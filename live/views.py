import json
from datetime import datetime, timedelta
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import viewsets, permissions, status, mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from livekit import api

from .models import LiveClass, LiveLesson, LessonResource
from courses.models import Course, Enrollment
from organizations.models import OrgMembership
from .permissions import IsTutorOrOrgAdmin
from .serializers import (
    LiveClassManagementSerializer,
    CourseLiveHubSerializer,
    LiveLessonSerializer,
    LessonResourceSerializer
)
from .services import LiveClassScheduler

LK_API_KEY = "devkey"
LK_API_SECRET = "SecureLiveKitSecretKey2026EvukaProject"
LK_SERVER_URL = "ws://127.0.0.1:7880"


class LiveClassManagementViewSet(viewsets.ModelViewSet):
    serializer_class = LiveClassManagementSerializer
    permission_classes = [permissions.IsAuthenticated, IsTutorOrOrgAdmin]
    lookup_field = "slug"

    def get_queryset(self):
        user = self.request.user
        active_org = getattr(self.request, "active_organization", None)
        course_slug = self.request.query_params.get('course_slug')

        qs = LiveClass.objects.select_related("course").prefetch_related("lessons")

        if active_org:
            membership = OrgMembership.objects.filter(user=user, organization=active_org).first()
            if not membership:
                return qs.none()
            if membership.role in ["admin", "owner"]:
                qs = qs.filter(organization=active_org)
            else:
                qs = qs.filter(organization=active_org, creator=user)
        else:
            qs = qs.filter(creator=user, organization__isnull=True)

        if course_slug:
            qs = qs.filter(course__slug=course_slug)

        return qs

    @transaction.atomic
    def perform_create(self, serializer):
        instance = serializer.save(
            creator=self.request.user,
            organization=getattr(self.request, "active_organization", None),
            creator_profile=getattr(self.request.user, "creator_profile", None)
        )
        scheduler = LiveClassScheduler(instance)
        scheduler.schedule_lessons(months_ahead=3)

    @transaction.atomic
    def perform_update(self, serializer):
        instance = serializer.save()
        scheduler = LiveClassScheduler(instance)
        scheduler.update_schedule()


class StudentLiveHubViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CourseLiveHubSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        active_org = getattr(self.request, "active_organization", None)

        enrolled_course_ids = Enrollment.objects.filter(
            user=user, status='active'
        ).values_list('course_id', flat=True)

        qs = Course.objects.filter(id__in=enrolled_course_ids).distinct()

        if active_org:
            qs = qs.filter(organization=active_org)
        else:
            qs = qs.filter(organization__isnull=True)

        return qs.prefetch_related('live_classes', 'live_classes__lessons')

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        now = timezone.now()

        live_now_count = LiveLesson.objects.filter(
            live_class__course__id__in=self.get_queryset().values_list('id', flat=True),
            start_datetime__lte=now + timedelta(minutes=20),
            end_datetime__gt=now,
            is_cancelled=False
        ).distinct().count()

        return Response({
            "live_now_count": live_now_count,
            "courses": response.data
        })


class LiveLessonViewSet(
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    queryset = LiveLesson.objects.select_related("live_class")
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = LiveLessonSerializer

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

        enrolled_course_ids = Enrollment.objects.filter(
            user=user, status="active"
        ).values_list("course_id", flat=True)

        qs = LiveLesson.objects.filter(live_class__course_id__in=enrolled_course_ids)
        if active_org:
            return qs.filter(live_class__organization=active_org)
        return qs.filter(live_class__organization__isnull=True)

    @action(detail=True, methods=["get"])
    def join(self, request, pk=None):
        lesson = self.get_object()
        user = request.user
        is_host = (user == lesson.live_class.creator)

        if not is_host:
            now = timezone.now()
            buffer_start = lesson.start_datetime - timedelta(minutes=20)

            if now < buffer_start:
                time_left = int((buffer_start - now).total_seconds() / 60)
                return Response({
                    "error": "too_early",
                    "message": f"Class opens in {time_left} minutes",
                    "open_at": buffer_start
                }, status=403)

        participant_identity = str(user.id)
        participant_name = user.get_full_name() or user.username
        room_name = lesson.chat_room_id
        host_identity = str(lesson.live_class.creator.id)

        metadata = json.dumps({
            "mic_locked": lesson.is_mic_locked,
            "camera_locked": lesson.is_camera_locked,
            "is_host": is_host
        })

        token = api.AccessToken(LK_API_KEY, LK_API_SECRET) \
            .with_identity(participant_identity) \
            .with_name(participant_name) \
            .with_metadata(metadata) \
            .with_grants(api.VideoGrants(
            room_join=True,
            room=room_name,
            can_publish=True,
            can_subscribe=True,
            can_publish_data=True,
        ))

        resources = lesson.resources.all()
        resource_data = LessonResourceSerializer(resources, many=True).data

        return Response({
            "token": token.to_jwt(),
            "url": LK_SERVER_URL,
            "is_host": is_host,
            "host_identity": host_identity,
            "effective_end_datetime": lesson.effective_end_datetime,
            "resources": resource_data
        })

    @action(detail=True, methods=["post"])
    def extend_time(self, request, pk=None):
        lesson = self.get_object()
        if request.user != lesson.live_class.creator:
            return Response({"error": "Unauthorized"}, status=403)

        add_minutes = int(request.data.get("minutes", 15))
        if lesson.extension_minutes + add_minutes > 60:
            return Response({"error": "Limit reached"}, status=400)

        lesson.extension_minutes += add_minutes
        lesson.save()
        return Response({"new_end_time": lesson.effective_end_datetime})

    @action(detail=True, methods=["post"])
    def toggle_lock(self, request, pk=None):
        lesson = self.get_object()
        if request.user != lesson.live_class.creator:
            return Response({"error": "Unauthorized"}, status=403)

        target = request.data.get("target")
        state = request.data.get("locked")

        if target == 'mic':
            lesson.is_mic_locked = state
        elif target == 'camera':
            lesson.is_camera_locked = state
        lesson.save()

        lkapi = api.LiveKitAPI(LK_SERVER_URL, LK_API_KEY, LK_API_SECRET)
        room_meta = json.dumps({"mic_locked": lesson.is_mic_locked, "camera_locked": lesson.is_camera_locked})

        try:
            lkapi.room.update_room_metadata(lesson.chat_room_id, metadata=room_meta)
        except:
            pass

        return Response({"status": "updated"})

    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser, FormParser])
    def upload_resource(self, request, pk=None):
        lesson = self.get_object()
        if request.user != lesson.live_class.creator:
            return Response({"error": "Unauthorized"}, status=403)

        file = request.FILES.get('file')
        if not file: return Response({"error": "No file"}, status=400)

        resource = LessonResource.objects.create(lesson=lesson, file=file, title=request.data.get('title', file.name))
        return Response(LessonResourceSerializer(resource).data)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        lesson = self.get_object()
        if request.user != lesson.live_class.creator:
            return Response({"error": "Unauthorized"}, status=403)
        lesson.is_cancelled = True
        lesson.save()
        return Response({"status": "cancelled"})