import json
import os
from datetime import datetime, timedelta
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.conf import settings
from rest_framework import viewsets, permissions, status, mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from asgiref.sync import async_to_sync
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

LK_API_KEY = os.getenv("LK_API_KEY")
LK_API_SECRET = os.getenv("LK_API_SECRET")
LK_SERVER_URL = os.getenv("LK_SERVER_URL")


class LiveClassManagementViewSet(viewsets.ModelViewSet):
    serializer_class = LiveClassManagementSerializer
    permission_classes = [permissions.IsAuthenticated, IsTutorOrOrgAdmin]
    lookup_field = "slug"

    def get_queryset(self):
        user = self.request.user
        active_org = getattr(self.request, "active_organization", None)
        course_slug = self.request.query_params.get('course_slug')

        if active_org:
            membership = OrgMembership.objects.filter(user=user, organization=active_org).first()
            if not membership:
                return LiveClass.objects.none()

            is_admin = membership.role in ["admin", "owner"]
            if is_admin:
                qs = LiveClass.objects.filter(organization=active_org)
            else:
                qs = LiveClass.objects.filter(organization=active_org, creator=user)
        else:
            qs = LiveClass.objects.filter(organization__isnull=True, creator=user)

        qs = qs.filter(course__status="published")

        if course_slug:
            qs = qs.filter(course__slug=course_slug)

        return qs.select_related("course").prefetch_related("lessons")

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


class LiveHubViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CourseLiveHubSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        active_org = getattr(self.request, "active_organization", None)

        base_qs = Course.objects.filter(status="published")

        if active_org:
            membership = OrgMembership.objects.filter(user=user, organization=active_org).first()
            if not membership:
                return Course.objects.none()

            is_admin = membership.role in ["admin", "owner"]
            if is_admin:
                courses_qs = base_qs.filter(organization=active_org)
            else:
                courses_qs = base_qs.filter(organization=active_org, creator=user)
        else:
            courses_qs = base_qs.filter(organization__isnull=True, creator=user)

        return courses_qs.distinct().prefetch_related('live_classes', 'live_classes__lessons')

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        now = timezone.now()
        buffer_time = now + timedelta(minutes=20)

        live_now_count = LiveLesson.objects.filter(
            live_class__course__in=queryset,
            start_datetime__lte=buffer_time,
            end_datetime__gt=now,
            is_cancelled=False
        ).distinct().count()

        return Response({
            "live_now_count": live_now_count,
            "courses": serializer.data
        })


class LiveLessonViewSet(
    mixins.CreateModelMixin,
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
        qs = LiveLesson.objects.select_related("live_class", "live_class__organization")
        qs = qs.filter(live_class__course__status="published")

        is_instructor_filter = Q(live_class__creator=user) | Q(live_class__course__instructors__in=[user])
        is_org_admin_filter = Q()
        if active_org:
            membership = OrgMembership.objects.filter(user=user, organization=active_org).first()
            if membership and membership.role in ["admin", "owner"]:
                is_org_admin_filter = Q(live_class__organization=active_org)

        enrolled_course_ids = Enrollment.objects.filter(
            user=user,
            status__in=["active", "completed"]
        ).values_list("course_id", flat=True)
        is_student_filter = Q(live_class__course_id__in=enrolled_course_ids)

        qs = qs.filter(is_instructor_filter | is_org_admin_filter | is_student_filter).distinct()
        if active_org:
            return qs.filter(live_class__organization=active_org)
        return qs.filter(live_class__organization__isnull=True)

    @action(detail=True, methods=["get"])
    def join(self, request, pk=None):
        lesson = self.get_object()
        user = request.user
        is_host = (user == lesson.live_class.creator or
                   lesson.live_class.course.instructors.filter(id=user.id).exists())

        if not is_host:
            now = timezone.now()
            buffer_start = lesson.start_datetime - timedelta(minutes=20)
            if now < buffer_start:
                time_left = int((buffer_start - now).total_seconds() / 60)
                return Response({
                    "error": "too_early",
                    "message": f"Class opens in {time_left} minutes",
                    "open_at": buffer_start
                }, status=status.HTTP_403_FORBIDDEN)

            # Trace Attendance: Add student to the attendees list upon successful join request
            if not lesson.attendees.filter(id=user.id).exists():
                lesson.attendees.add(user)

        participant_identity = str(user.id)
        participant_name = user.get_full_name() or user.username
        room_name = str(lesson.chat_room_id)
        host_identity = str(lesson.live_class.creator.id)

        metadata = json.dumps({
            "mic_locked": lesson.is_mic_locked,
            "camera_locked": lesson.is_camera_locked,
            "screen_locked": getattr(lesson, 'is_screen_locked', False),
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

        return Response({
            "token": token.to_jwt(),
            "url": LK_SERVER_URL,
            "is_host": is_host,
            "host_identity": host_identity,
            "course_slug": lesson.live_class.course.slug,
            "effective_end_datetime": lesson.effective_end_datetime,
            "resources": LessonResourceSerializer(lesson.resources.all(), many=True).data,
            "mic_locked": lesson.is_mic_locked,
            "camera_locked": lesson.is_camera_locked,
            "screen_locked": getattr(lesson, 'is_screen_locked', False)
        })

    @action(detail=True, methods=["post"])
    def toggle_lock(self, request, pk=None):
        lesson = self.get_object()
        if request.user != lesson.live_class.creator and not lesson.live_class.course.instructors.filter(
                id=request.user.id).exists():
            return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)

        target, state = request.data.get("target"), request.data.get("locked")
        if target == 'mic':
            lesson.is_mic_locked = state
        elif target == 'camera':
            lesson.is_camera_locked = state
        elif target == 'screen':
            lesson.is_screen_locked = state
        lesson.save()

        room_id = str(lesson.chat_room_id)

        async def lk_sync():
            lkapi = api.LiveKitAPI(LK_SERVER_URL, LK_API_KEY, LK_API_SECRET)
            try:
                payload_dict = {
                    "mic_locked": lesson.is_mic_locked,
                    "camera_locked": lesson.is_camera_locked,
                    "screen_locked": getattr(lesson, 'is_screen_locked', False)
                }
                metadata_str = json.dumps(payload_dict)

                await lkapi.room.update_room_metadata(api.UpdateRoomMetadataRequest(
                    room=room_id,
                    metadata=metadata_str
                ))

                signal_content = json.dumps({
                    "type": "PERMISSION_UPDATE",
                    **payload_dict
                })

                await lkapi.room.send_data(api.SendDataRequest(
                    room=room_id,
                    data=signal_content.encode(),
                    kind=api.DataPacket.RELIABLE
                ))
            finally:
                await lkapi.aclose()

        try:
            async_to_sync(lk_sync)()
        except:
            pass

        return Response({
            "status": "updated",
            "mic_locked": lesson.is_mic_locked,
            "camera_locked": lesson.is_camera_locked,
            "screen_locked": getattr(lesson, 'is_screen_locked', False)
        })

    @action(detail=True, methods=["post"])
    def acknowledge_student(self, request, pk=None):
        lesson = self.get_object()
        if request.user != lesson.live_class.creator and not lesson.live_class.course.instructors.filter(
                id=request.user.id).exists():
            return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)

        student_identity = request.data.get("student_identity")
        action_type = request.data.get("action") # 'grant' or 'revoke'

        async def lk_acknowledge():
            lkapi = api.LiveKitAPI(LK_SERVER_URL, LK_API_KEY, LK_API_SECRET)
            try:
                signal_type = "CLEAR_HANDS" if action_type == 'revoke' else "TUTOR_ACKNOWLEDGE"
                payload = json.dumps({
                    "type": signal_type,
                    "mic_locked": lesson.is_mic_locked if action_type == 'revoke' else False,
                    "camera_locked": lesson.is_camera_locked if action_type == 'revoke' else False,
                    "screen_locked": getattr(lesson, 'is_screen_locked', False) if action_type == 'revoke' else False,
                })
                await lkapi.room.send_data(api.SendDataRequest(
                    room=str(lesson.chat_room_id),
                    data=payload.encode(),
                    kind=api.DataPacket.RELIABLE,
                    destination_identities=[student_identity]
                ))
            finally:
                await lkapi.aclose()

        try:
            async_to_sync(lk_acknowledge)()
        except:
            pass

        return Response({"status": "acknowledged"})

    @action(detail=True, methods=["post"])
    def extend_time(self, request, pk=None):
        lesson = self.get_object()
        if request.user != lesson.live_class.creator and not lesson.live_class.course.instructors.filter(
                id=request.user.id).exists():
            return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)

        add_minutes = int(request.data.get("minutes", 15))
        lesson.extension_minutes += add_minutes
        lesson.save()

        async def lk_extend():
            lkapi = api.LiveKitAPI(LK_SERVER_URL, LK_API_KEY, LK_API_SECRET)
            try:
                payload = json.dumps({
                    "type": "TIME_EXTENDED",
                    "new_end_time": lesson.effective_end_datetime.isoformat(),
                    "minutes": add_minutes
                })
                await lkapi.room.send_data(api.SendDataRequest(
                    room=str(lesson.chat_room_id),
                    data=payload.encode(),
                    kind=api.DataPacket.RELIABLE
                ))
            finally:
                await lkapi.aclose()

        try:
            async_to_sync(lk_extend)()
        except:
            pass

        return Response({"new_end_time": lesson.effective_end_datetime})

    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser, FormParser])
    def upload_resource(self, request, pk=None):
        lesson = self.get_object()
        if request.user != lesson.live_class.creator and not lesson.live_class.course.instructors.filter(
                id=request.user.id).exists():
            return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)

        file = request.FILES.get('file')
        if not file: return Response({"error": "No file"}, status=status.HTTP_400_BAD_REQUEST)

        resource = LessonResource.objects.create(lesson=lesson, file=file, title=request.data.get('title', file.name))
        resource_data = LessonResourceSerializer(resource).data

        async def lk_resource():
            lkapi = api.LiveKitAPI(LK_SERVER_URL, LK_API_KEY, LK_API_SECRET)
            try:
                payload = json.dumps({"type": "RESOURCE_ADDED", "resource": resource_data})
                await lkapi.room.send_data(api.SendDataRequest(
                    room=str(lesson.chat_room_id),
                    data=payload.encode(),
                    kind=api.DataPacket.RELIABLE
                ))
            finally:
                await lkapi.aclose()

        try:
            async_to_sync(lk_resource)()
        except:
            pass

        return Response(resource_data)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        lesson = self.get_object()
        if request.user != lesson.live_class.creator:
            return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)
        lesson.is_cancelled = True
        lesson.save()
        return Response({"status": "cancelled"})


