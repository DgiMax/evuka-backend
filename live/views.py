from rest_framework import viewsets, permissions, status, mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from datetime import datetime, timedelta, date
import calendar
from django.db import transaction

from courses.views import TutorCourseViewSet
from organizations.models import OrgMembership
from .models import LiveClass, LiveLesson
from .serializers import LiveClassSerializer, LiveLessonSerializer, CourseWithLiveClassesSerializer, \
    LiveLessonCreateSerializer
from .permissions import IsTutorOrOrgAdmin
from .utils.jitsi_token import generate_jitsi_token
from django.conf import settings


class LiveClassViewSet(viewsets.ModelViewSet):
    queryset = LiveClass.objects.all()
    serializer_class = LiveClassSerializer
    permission_classes = [permissions.IsAuthenticated, IsTutorOrOrgAdmin]
    lookup_field = "slug"
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["title", "description"]
    ordering_fields = ["start_date", "created_at"]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context.update({"request": self.request})
        return context

    def get_queryset(self):
        user = self.request.user
        active_org = getattr(self.request, "active_organization", None)
        qs = LiveClass.objects.select_related("organization", "creator", "course").prefetch_related("lessons")

        if active_org:
            membership = OrgMembership.objects.filter(user=user, organization=active_org).first()
            if not membership:
                return qs.none()
            if membership.role in ["admin", "owner"]:
                return qs.filter(organization=active_org)
            return qs.filter(organization=active_org, creator=user)
        return qs.filter(creator=user, organization__isnull=True)

    @transaction.atomic
    def perform_create(self, serializer):
        user = self.request.user
        active_org = getattr(self.request, "active_organization", None)
        instance = serializer.save(
            creator=user,
            organization=active_org,
            creator_profile=getattr(user, "creator_profile", None),
        )

        if instance.recurrence_type == "weekly" and instance.recurrence_days:
            instance.generate_lessons_batch(start_from=instance.start_date, days_ahead=30)

        elif instance.recurrence_type == "none":
            self._generate_one_time_lesson(instance)

    @transaction.atomic
    def perform_update(self, serializer):
        instance = serializer.save()
        mode = instance.recurrence_update_mode

        if instance.recurrence_type == "weekly" and instance.recurrence_days:
            if mode == "all":
                instance.lessons.all().delete()
                instance.generate_lessons_batch(start_from=instance.start_date, days_ahead=30)

            elif mode == "future":
                instance.lessons.filter(date__gte=date.today()).delete()
                instance.generate_lessons_batch(start_from=date.today(), days_ahead=30)

        elif instance.recurrence_type == "none":
            instance.lessons.filter(date__gte=date.today()).delete()

        if mode != 'none':
            instance.recurrence_update_mode = 'none'
            instance.save(update_fields=['recurrence_update_mode'])

    def _generate_one_time_lesson(self, live_class):
        """Generates exactly one lesson for a non-recurring LiveClass."""
        # Even for one-time, we expect the frontend to send the time in recurrence_days
        # e.g., recurrence_days = {"Monday": "14:00"} or just a simple dict {"time": "14:00"}
        # Depending on your frontend implementation.

        # If your frontend sends {"Monday": "10:00"} matching the start_date weekday:
        start_date = live_class.start_date
        weekday = calendar.day_name[start_date.weekday()]
        time_str = live_class.recurrence_days.get(weekday)

        if not time_str:
            time_str = live_class.recurrence_days.get('time')

        if time_str:
            start_time = datetime.strptime(time_str, "%H:%M").time()
            end_time = (datetime.combine(date.today(), start_time) +
                        timedelta(minutes=live_class.lesson_duration)).time()

            LiveLesson.objects.create(
                live_class=live_class,
                title=f"{live_class.title}",
                date=start_date,
                start_time=start_time,
                end_time=end_time
            )

    def _generate_lessons(self, live_class, start_date=None):
        if live_class.recurrence_type != "weekly" or not live_class.recurrence_days:
            return

        start = start_date or live_class.start_date
        end = live_class.end_date or (live_class.start_date + timedelta(weeks=8))

        if start > end:
            return

        days_map = {day: time for day, time in live_class.recurrence_days.items()}
        current = start

        while current <= end:
            weekday = calendar.day_name[current.weekday()]
            if weekday in days_map:
                time_str = days_map[weekday]
                start_time = datetime.strptime(time_str, "%H:%M").time()
                end_time = (
                        datetime.combine(date.today(), start_time) +
                        timedelta(minutes=live_class.lesson_duration)
                ).time()

                LiveLesson.objects.create(
                    live_class=live_class,
                    title=f"{live_class.title} - {weekday} Session",
                    date=current,
                    start_time=start_time,
                    end_time=end_time,
                )
            current += timedelta(days=1)

    @action(detail=True, methods=["get"], permission_classes=[permissions.IsAuthenticated])
    def join(self, request, slug=None):
        live_class = self.get_object()
        user = request.user

        if not live_class.can_join(user):
            return Response({"error": "Not allowed to join"}, status=403)

        token = None
        is_moderator = False
        room_name = live_class.get_jitsi_room_name()
        domain = getattr(settings, "JITSI_DOMAIN", "meet.e-vuka.com")

        if live_class.requires_auth:
            is_moderator = (user.id == live_class.creator.id)
            token = generate_jitsi_token(
                user,
                room_name,
                is_moderator=is_moderator
            )

        data = {
            "domain": domain,
            "room_name": room_name,
            "jwt": token,
            "user_info": {
                "displayName": user.get_full_name(),
                "email": user.email,
            },
            "config_overwrite": {
                "startWithAudioMuted": True,
                "startWithVideoMuted": True,
                "prejoinPageEnabled": False,
                "toolbarButtons": [
                    'microphone', 'camera', 'closedcaptions', 'desktop', 'fullscreen',
                    'fodeviceselection', 'hangup', 'profile', 'chat', 'recording',
                    'livestreaming', 'etherpad', 'sharedvideo', 'settings', 'raisehand',
                    'videoquality', 'filmstrip', 'invite', 'feedback', 'stats', 'shortcuts',
                    'tileview', 'videobackgroundblur', 'download', 'help', 'mute-everyone',
                    'security'
                ] if is_moderator else [
                    'microphone', 'camera', 'desktop', 'fullscreen',
                    'fodeviceselection', 'hangup', 'chat', 'raisehand',
                    'videoquality', 'tileview', 'settings'
                ]
            }
        }
        return Response(data, status=200)


class LiveLessonViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    queryset = LiveLesson.objects.select_related("live_class")
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'create':
            return LiveLessonCreateSerializer
        return LiveLessonSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context.update({"request": self.request})
        return context

    def get_permissions(self):
        if self.action in ["create", "update", "partial_update", "destroy"]:
            self.permission_classes = [permissions.IsAuthenticated, IsTutorOrOrgAdmin]
        else:
            self.permission_classes = [permissions.IsAuthenticated]
        return super().get_permissions()

    def get_queryset(self):
        user = self.request.user
        active_org = getattr(self.request, "active_organization", None)

        is_tutor_or_admin = IsTutorOrOrgAdmin().has_permission(self.request, self)

        if is_tutor_or_admin:
            qs = LiveLesson.objects.select_related("live_class", "live_class__organization")
            if active_org:
                membership = OrgMembership.objects.filter(user=user, organization=active_org).first()
                if not membership:
                    return qs.none()
                if membership.role in ["admin", "owner"]:
                    return qs.filter(live_class__organization=active_org)
                return qs.filter(live_class__organization=active_org, live_class__creator=user)
            return qs.filter(live_class__creator=user, live_class__organization__isnull=True)

        try:
            from courses.models import Enrollment
            enrolled_course_ids = Enrollment.objects.filter(user=user, status="active").values_list("course_id",
                                                                                                    flat=True)
            qs = LiveLesson.objects.filter(live_class__course_id__in=enrolled_course_ids)

            if active_org:
                return qs.filter(live_class__organization=active_org)
            return qs.filter(live_class__organization__isnull=True)

        except ImportError:
            return LiveLesson.objects.none()

    @action(detail=True, methods=["get"], permission_classes=[permissions.IsAuthenticated])
    def join(self, request, pk=None):
        try:
            lesson = self.get_object()
            user = request.user
            live_class = lesson.live_class

            if not live_class.can_join(user):
                return Response({"error": "Not allowed to join"}, status=status.HTTP_403_FORBIDDEN)

            # 1. Get Domain and Room
            domain = getattr(settings, "JITSI_DOMAIN", "meet.e-vuka.com")
            room_name = lesson.jitsi_room_name

            # 2. Generate Token (If auth required)
            token = None
            is_moderator = False
            if live_class.requires_auth:
                is_moderator = (user.id == live_class.creator.id)
                # Ensure you have generate_jitsi_token imported!
                token = generate_jitsi_token(
                    user,
                    room_name,
                    is_moderator=is_moderator
                )

            # 3. Construct the NEW response format
            data = {
                "domain": domain,
                "room_name": room_name,
                "jwt": token,
                "user_info": {
                    "displayName": user.get_full_name() or user.username,
                    "email": user.email,
                },
                "config_overwrite": {
                    "startWithAudioMuted": True,
                    "startWithVideoMuted": True,
                    "prejoinPageEnabled": False,
                    # Tutors get admin tools, Students get basic tools
                    "toolbarButtons": [
                        'microphone', 'camera', 'closedcaptions', 'desktop', 'fullscreen',
                        'fodeviceselection', 'hangup', 'profile', 'chat', 'recording',
                        'livestreaming', 'etherpad', 'sharedvideo', 'settings', 'raisehand',
                        'videoquality', 'filmstrip', 'invite', 'feedback', 'stats', 'shortcuts',
                        'tileview', 'videobackgroundblur', 'download', 'help', 'mute-everyone',
                        'security'
                    ] if is_moderator else [
                        'microphone', 'camera', 'desktop', 'fullscreen',
                        'fodeviceselection', 'hangup', 'chat', 'raisehand',
                        'videoquality', 'tileview', 'settings'
                    ]
                }
            }

            return Response(data)

        except Exception as e:
            print(f"Join Error: {e}")  # Print error to server logs for debugging
            return Response({"error": "An internal error occurred."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class AllLiveClassesViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CourseWithLiveClassesSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        tutor_course_view = TutorCourseViewSet(request=self.request)
        base_course_qs = tutor_course_view.get_queryset()

        return base_course_qs.prefetch_related(
            'live_classes'
        ).order_by('-created_at')