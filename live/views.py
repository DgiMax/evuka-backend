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
from .serializers import LiveClassSerializer, LiveLessonSerializer, CourseWithLiveClassesSerializer
from .permissions import IsTutorOrOrgAdmin
from .utils.jitsi_token import generate_jitsi_token


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
            self._generate_lessons(instance)

    @transaction.atomic
    def perform_update(self, serializer):
        instance = serializer.save()
        mode = instance.recurrence_update_mode

        if instance.recurrence_type == "weekly" and instance.recurrence_days:
            if mode == "all":
                instance.lessons.all().delete()
                self._generate_lessons(instance)
            elif mode == "future":
                instance.lessons.filter(date__gte=date.today()).delete()
                self._generate_lessons(instance, start_date=date.today())
        elif instance.recurrence_type == "none":
            instance.lessons.filter(date__gte=date.today()).delete()

        if mode != 'none':
            instance.recurrence_update_mode = 'none'
            instance.save(update_fields=['recurrence_update_mode'])

    def _generate_one_time_lesson(self, live_class):
        """Generates exactly one lesson for a non-recurring LiveClass."""
        if not live_class.recurrence_days:
            return

        start_date = live_class.start_date
        weekday = calendar.day_name[start_date.weekday()]

        time_str = live_class.recurrence_days.get(weekday)

        if time_str:
            self._generate_lesson_instance(
                live_class,
                start_date,
                time_str,
                "One-Time Session"
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

        if live_class.requires_auth:
            is_moderator = (user.id == live_class.creator.id)

            token = generate_jitsi_token(
                user,
                live_class.get_jitsi_room_name(),
                is_moderator=is_moderator
            )

        join_url = f"{live_class.meeting_link}?jwt={token}" if token else live_class.meeting_link
        return Response({"meeting_url": join_url}, status=200)


class LiveLessonViewSet(
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    queryset = LiveLesson.objects.select_related("live_class")
    serializer_class = LiveLessonSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context.update({"request": self.request})
        return context

    def get_permissions(self):
        if self.action in ["update", "partial_update", "destroy"]:
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

            token = None

            if live_class.requires_auth:
                is_moderator = (user.id == live_class.creator.id)

                token = generate_jitsi_token(
                    user,
                    lesson.jitsi_room_name,
                    is_moderator=is_moderator
                )

            join_url = f"{lesson.jitsi_meeting_link}?jwt={token}" if token else lesson.jitsi_meeting_link
            return Response({"meeting_url": join_url})

        except Exception:
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