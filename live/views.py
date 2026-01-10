import uuid
from datetime import datetime, timedelta, date
import calendar
from django.db import transaction
from django.conf import settings
from rest_framework import viewsets, permissions, status, mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend

from courses.views import TutorCourseViewSet
from organizations.models import OrgMembership
from courses.models import Enrollment
from .models import LiveClass, LiveLesson
from .serializers import (
    LiveClassSerializer,
    LiveLessonSerializer,
    CourseWithLiveClassesSerializer,
    LiveLessonCreateSerializer
)
from .permissions import IsTutorOrOrgAdmin
from .utils.tokens import generate_live_service_token
from .utils.bunny import get_or_create_bunny_stream


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

            # 1. Determine Permission
            is_creator = (user == live_class.creator)
            if live_class.organization and live_class.organization.owner == user:
                is_creator = True

            if not is_creator:
                has_enrollment = Enrollment.objects.filter(
                    user=user,
                    course=live_class.course,
                    status="active"
                ).exists()

                if not has_enrollment:
                    return Response(
                        {"detail": "You must be enrolled in this course to join."},
                        status=status.HTTP_403_FORBIDDEN
                    )

            role = "host" if is_creator else "student"

            # 2. Generate WebSocket Token
            ws_token = generate_live_service_token(
                user=user,
                room_id=lesson.chat_room_id,
                role=role
            )

            # 3. Generate Stream Key (Internal)
            # We no longer ask Bunny. We generate a unique ID for our Nginx server.
            if not lesson.stream_key:
                # Create a simple unique string (e.g., "lesson_25_a1b2c3")
                lesson.stream_key = f"lesson_{lesson.id}_{uuid.uuid4().hex[:6]}"
                lesson.save()

            # 4. Configuration for Self-Hosted Media Server
            # This IP is your current Public/Hotspot IP where Docker is running.
            SERVER_IP = "89.187.169.205"

            video_config = {}

            if role == "host":
                video_config = {
                    "mode": "broadcast",
                    "protocol": "rtmp",
                    # The frontend sends data to FastAPI via WebSocket.
                    # FastAPI pushes to this URL. We send it here just for reference/debugging.
                    "ingest_url": f"rtmp://{SERVER_IP}/live",
                    "stream_key": lesson.stream_key,
                }
            else:
                video_config = {
                    "mode": "playback",
                    "protocol": "hls",
                    # Student watches directly from your Nginx container's HTTP port (8080)
                    "playback_url": f"http://{SERVER_IP}:8090/hls/{lesson.stream_key}.m3u8",
                }

            response_data = {
                "lesson_id": lesson.id,
                "chat_room_id": lesson.chat_room_id,
                "user_role": role,
                "live_service": {
                    "url": getattr(settings, "LIVE_SOCKET_URL", "ws://127.0.0.1:8001"),
                    "token": ws_token
                },
                "video": video_config,
                "meta": {
                    "title": lesson.title,
                    "tutor_name": live_class.creator.get_full_name()
                }
            }

            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            print(f"Join Error: {e}")
            return Response(
                {"detail": "Unable to join live session."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AllLiveClassesViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CourseWithLiveClassesSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        tutor_course_view = TutorCourseViewSet(request=self.request)
        base_course_qs = tutor_course_view.get_queryset()
        return base_course_qs.prefetch_related('live_classes').order_by('-created_at')