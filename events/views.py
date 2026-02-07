import json
import os
from datetime import datetime, timedelta
from django.http import HttpResponse
from django.utils import timezone
from django.db.models import Q, Count, F
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAuthenticatedOrReadOnly
from livekit import api
from django.shortcuts import get_object_or_404
from rest_framework.parsers import MultiPartParser, FormParser
from asgiref.sync import async_to_sync
from livekit import api as lk_api

from courses.models import Course, OrgCategory, GlobalSubCategory, Enrollment
from organizations.models import OrgMembership, Organization
from .filters import EventFilter
from .models import Event, EventRegistration, EventAttachment
from .serializers import (
    EventSerializer,
    EventListSerializer,
    EventRegistrationSerializer,
    TutorEventDetailSerializer,
    CreateEventSerializer,
    FeaturedEventSerializer,
)
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from .utils import generate_event_ticket_pdf

LK_API_KEY = os.getenv("LK_API_KEY")
LK_API_SECRET = os.getenv("LK_API_SECRET")
LK_SERVER_URL = os.getenv("LK_SERVER_URL")


class BestUpcomingEventView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        user = request.user
        now = timezone.now()
        active_org = getattr(request, "active_organization", None)

        queryset = Event.objects.select_related("course", "course__organization").filter(
            event_status__in=["approved", "scheduled"],
            start_time__gt=now,
            registration_open=True
        ).filter(
            Q(registration_deadline__isnull=True) | Q(registration_deadline__gt=now)
        )

        queryset = queryset.annotate(
            confirmed_count=Count(
                "registrations",
                filter=Q(registrations__status="registered"),
                distinct=True
            )
        ).filter(
            Q(max_attendees__isnull=True) | Q(confirmed_count__lt=F("max_attendees"))
        )

        if active_org:
            queryset = queryset.filter(course__organization=active_org)
        else:
            queryset = queryset.filter(course__organization__isnull=True)

        if user.is_authenticated:
            registered_event_ids = EventRegistration.objects.filter(
                user=user,
                status="registered"
            ).values_list("event_id", flat=True)
            queryset = queryset.exclude(id__in=registered_event_ids)

            eligibility_filter = Q(who_can_join="anyone")

            active_enrollments = Enrollment.objects.filter(
                user=user,
                status="active"
            ).values_list("course_id", flat=True)
            eligibility_filter |= Q(who_can_join="course_students", course_id__in=active_enrollments)

            active_memberships = OrgMembership.objects.filter(
                user=user,
                is_active=True
            ).values_list("organization_id", flat=True)
            eligibility_filter |= Q(who_can_join="org_students", course__organization_id__in=active_memberships)

            queryset = queryset.filter(eligibility_filter)
        else:
            queryset = queryset.filter(who_can_join="anyone")

        best_event = queryset.order_by("start_time", "-confirmed_count").first()

        if not best_event:
            return Response(
                {"detail": "No eligible upcoming events found at this time."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = FeaturedEventSerializer(best_event, context={'request': request})
        return Response(serializer.data)


class PublicEventViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Public-facing viewset for Events.
    Follows the manual filtering pattern for consistency across the platform.
    """
    serializer_class = EventSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    lookup_field = "slug"

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = EventFilter
    search_fields = ["title", "overview", "description"]
    ordering_fields = ["start_time", "created_at", "price"]

    def get_serializer_class(self):
        if self.action == "list":
            return EventListSerializer
        return EventSerializer

    def get_queryset(self):
        """
        Base queryset handling Organization logic and base status filtering.
        Manual query_param filtering has been moved to EventFilter.
        """
        user = self.request.user
        active_org = getattr(self.request, "active_organization", None)
        now = timezone.now()

        queryset = (
            Event.objects.select_related(
                "course",
                "organizer",
                "course__global_subcategory",
                "course__org_category"
            )
            .prefetch_related("agenda", "attachments", "learning_objectives", "rules")
        )

        queryset = queryset.filter(
            event_status="approved",
            end_time__gte=now,
            registration_open=True
        ).filter(
            Q(registration_deadline__isnull=True) | Q(registration_deadline__gt=now)
        ).annotate(
            confirmed_count=Count(
                "registrations",
                filter=Q(registrations__status="registered"),
                distinct=True
            )
        ).filter(
            Q(max_attendees__isnull=True) | Q(confirmed_count__lt=F("max_attendees"))
        )

        if active_org:
            queryset = queryset.filter(course__organization=active_org)
        else:
            queryset = queryset.filter(course__organization__isnull=True)

        if user.is_authenticated:
            registered_ids = EventRegistration.objects.filter(
                user=user,
                status="registered"
            ).values_list("event_id", flat=True)
            queryset = queryset.exclude(id__in=registered_ids)

            active_enrollments = Enrollment.objects.filter(
                user=user,
                status="active"
            ).values_list("course_id", flat=True)

            active_memberships = OrgMembership.objects.filter(
                user=user,
                is_active=True
            ).values_list("organization_id", flat=True)

            eligibility_filter = Q(who_can_join="anyone")
            eligibility_filter |= Q(who_can_join="course_students", course_id__in=active_enrollments)
            eligibility_filter |= Q(who_can_join="org_students", course__organization_id__in=active_memberships)

            queryset = queryset.filter(eligibility_filter)
        else:
            queryset = queryset.filter(who_can_join="anyone")

        return queryset.order_by("start_time")

    def list(self, request, *args, **kwargs):
        """
        Manual list implementation to maintain pattern consistency.
        Uses the 'Double-Get' approach for safety.
        """
        queryset = self.get_queryset()
        filterset = self.filterset_class(request.query_params, queryset=queryset, request=request)

        if not filterset.is_valid():
            pass

        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def register(self, request, slug=None):
        event = self.get_object()

        if not event.can_user_register(request.user):
            return Response(
                {"detail": "Registration not allowed for this event."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if EventRegistration.objects.filter(event=event, user=request.user, status="registered").exists():
            return Response(
                {"detail": "You are already registered for this event."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payment_status = "pending" if event.is_paid else "free"

        serializer = EventRegistrationSerializer(
            data={"event": event.id, "payment_status": payment_status},
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class TutorEventViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    lookup_field = "slug"

    def get_serializer_class(self):
        if self.action == 'list':
            return EventListSerializer
        if self.action in ['create', 'update', 'partial_update']:
            return CreateEventSerializer
        if self.action == 'retrieve':
            return TutorEventDetailSerializer
        if self.action == 'attendees':
            return EventRegistrationSerializer
        return TutorEventDetailSerializer

    def get_queryset(self):
        user = self.request.user
        active_org = getattr(self.request, "active_organization", None)

        base_qs = Event.objects.select_related(
            "course", "organizer"
        ).order_by("-start_time")

        if active_org:
            membership = user.memberships.filter(organization=active_org, is_active=True).first()
            is_admin = membership and membership.role in ["admin", "owner"]
            if is_admin:
                queryset = base_qs.filter(course__organization=active_org)
            else:
                queryset = base_qs.filter(course__organization=active_org, organizer=user)
        else:
            queryset = base_qs.filter(course__organization__isnull=True, organizer=user)

        search_term = self.request.query_params.get("search")
        status_filter = self.request.query_params.get("status")

        if search_term:
            queryset = queryset.filter(title__icontains=search_term)

        if status_filter and status_filter != 'all':
            if status_filter in ["draft", "pending_approval", "approved", "cancelled", "postponed"]:
                queryset = queryset.filter(event_status=status_filter)

        return queryset

    async def _lk_broadcast(self, room_id, payload_dict, destination_identities=None):
        lkapi = lk_api.LiveKitAPI(LK_SERVER_URL, LK_API_KEY, LK_API_SECRET)
        try:
            payload = json.dumps(payload_dict)

            if payload_dict.get("type") == "PERMISSION_UPDATE":
                await lkapi.room.update_room_metadata(lk_api.UpdateRoomMetadataRequest(
                    room=room_id,
                    metadata=payload
                ))

            await lkapi.room.send_data(lk_api.SendDataRequest(
                room=room_id,
                data=payload.encode(),
                kind=lk_api.DataPacket.RELIABLE,
                destination_identities=destination_identities
            ))
        finally:
            await lkapi.aclose()

    @action(detail=True, methods=["get"])
    def join(self, request, slug=None):
        event = self.get_object()
        user = request.user
        is_host = (user == event.organizer)

        token = lk_api.AccessToken(LK_API_KEY, LK_API_SECRET) \
            .with_identity(str(user.id)) \
            .with_name(user.get_full_name() or user.username) \
            .with_grants(lk_api.VideoGrants(
            room_join=True,
            room=event.chat_room_id,
            can_publish=True,
            can_subscribe=True,
        ))

        resources_data = [
            {"id": res.id, "title": res.file.name.split('/')[-1], "file": request.build_absolute_uri(res.file.url)}
            for res in event.attachments.all()
        ]

        return Response({
            "token": token.to_jwt(),
            "url": LK_SERVER_URL,
            "is_host": True,
            "host_identity": str(user.id),
            "effective_end_datetime": event.end_time.isoformat() if event.end_time else None,
            "resources": resources_data,
            "mic_locked": getattr(event, 'mic_locked', False),
            "camera_locked": getattr(event, 'camera_locked', False),
            "screen_locked": getattr(event, 'screen_locked', False),
            "type": "native"
        })

    @action(detail=True, methods=["post"])
    def toggle_lock(self, request, slug=None):
        event = self.get_object()
        target = request.data.get('target')
        locked = request.data.get('locked', False)

        if target == 'mic':
            event.mic_locked = locked
        elif target == 'camera':
            event.camera_locked = locked
        elif target == 'screen':
            event.screen_locked = locked
        else:
            return Response({"error": "Invalid target"}, status=400)

        event.save()

        payload = {
            "type": "PERMISSION_UPDATE",
            "mic_locked": event.mic_locked,
            "camera_locked": event.camera_locked,
            "screen_locked": event.screen_locked
        }

        try:
            async_to_sync(self._lk_broadcast)(str(event.chat_room_id), payload)
        except:
            pass

        return Response({"status": "updated", **payload})

    @action(detail=True, methods=["post"])
    def acknowledge_student(self, request, slug=None):
        event = self.get_object()
        student_identity = request.data.get('student_identity')
        action_type = request.data.get('action')

        payload = {
            "type": "TUTOR_ACKNOWLEDGE" if action_type == 'grant' else "CLEAR_HANDS",
            "mic_locked": False if action_type == 'grant' else event.mic_locked,
            "camera_locked": False if action_type == 'grant' else event.camera_locked,
            "screen_locked": False if action_type == 'grant' else event.screen_locked,
        }

        try:
            async_to_sync(self._lk_broadcast)(
                str(event.chat_room_id),
                payload,
                destination_identities=[student_identity]
            )
        except:
            pass

        return Response({"status": "acknowledged"})

    @action(detail=True, methods=["post"])
    def extend_time(self, request, slug=None):
        event = self.get_object()
        minutes = int(request.data.get('minutes', 15))

        if not event.end_time:
            event.end_time = timezone.now()

        event.end_time += timedelta(minutes=minutes)
        event.save()

        payload = {
            "type": "TIME_EXTENDED",
            "new_end_time": event.end_time.isoformat(),
            "minutes": minutes
        }

        try:
            async_to_sync(self._lk_broadcast)(str(event.chat_room_id), payload)
        except:
            pass

        return Response({"status": "extended", "new_end_time": event.end_time.isoformat()})

    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser, FormParser])
    def upload_resource(self, request, slug=None):
        event = self.get_object()
        file_obj = request.FILES.get('file')

        if not file_obj:
            return Response({"error": "No file provided"}, status=400)

        attachment = EventAttachment.objects.create(
            event=event,
            file=file_obj,
            uploaded_by=request.user
        )

        resource_data = {
            "id": attachment.id,
            "title": request.data.get('title', file_obj.name),
            "file": request.build_absolute_uri(attachment.file.url)
        }

        try:
            async_to_sync(self._lk_broadcast)(
                str(event.chat_room_id),
                {"type": "RESOURCE_ADDED", "resource": resource_data}
            )
        except:
            pass

        return Response(resource_data)

    @action(detail=True, methods=["post"])
    def delete_resource(self, request, slug=None):
        resource_id = request.data.get('resource_id')
        attachment = get_object_or_404(EventAttachment, id=resource_id, event__slug=slug)
        attachment.delete()
        return Response({"status": "deleted"})

    def perform_create(self, serializer):
        user = self.request.user
        active_org = getattr(self.request, "active_organization", None)
        course = serializer.validated_data["course"]

        if active_org:
            membership = user.memberships.filter(organization=active_org, is_active=True).first()
            if not membership:
                raise PermissionDenied("You are not a member of this organization.")

            is_admin = membership.role in ["admin", "owner"]
            if not is_admin and course.creator != user:
                raise PermissionDenied("You can only create events for your own courses.")
            if course.organization != active_org:
                raise PermissionDenied("This course does not belong to this organization.")
        else:
            if course.organization is not None or course.creator != user:
                raise PermissionDenied("You can only create events for your own personal courses.")

        serializer.save(organizer=course.creator)

    def perform_update(self, serializer):
        user = self.request.user
        event = self.get_object()
        course = serializer.validated_data.get("course", event.course)
        active_org = getattr(self.request, "active_organization", None)

        if active_org:
            membership = user.memberships.filter(organization=active_org, is_active=True).first()
            if not membership:
                raise PermissionDenied("You are not a member of this organization.")

            is_admin = membership.role in ["admin", "owner"]
            if not is_admin and course.creator != user:
                raise PermissionDenied("You can only update events for your own courses.")
            if course.organization != active_org:
                raise PermissionDenied("This course does not belong to this organization.")
        else:
            if course.organization is not None or course.creator != user:
                raise PermissionDenied("You can only update events for your own personal courses.")

        serializer.save()

    @action(detail=True, methods=["get"])
    def attendees(self, request, slug=None):
        event = self.get_object()
        active_org = getattr(self.request, "active_organization", None)
        user = request.user

        is_organizer = user == event.organizer
        is_org_admin = False
        if active_org:
            is_org_admin = user.memberships.filter(
                organization=active_org, role__in=["admin", "owner"], is_active=True
            ).exists()

        if not (is_organizer or is_org_admin):
            raise PermissionDenied("You do not have permission to view attendees.")

        registrations = event.registrations.filter(status="registered").select_related("user")
        serializer = self.get_serializer(registrations, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def form_options(self, request):
        user = request.user
        active_org = getattr(request, "active_organization", None)

        if active_org:
            membership = user.memberships.filter(
                organization=active_org, is_active=True
            ).first()
            is_admin_or_owner = membership and membership.role in ["admin", "owner"]

            if is_admin_or_owner:
                courses = Course.objects.filter(organization=active_org, status='published')
            else:
                courses = Course.objects.filter(organization=active_org, creator=user, status='published')
        else:
            is_admin_or_owner = False
            courses = Course.objects.filter(creator=user, organization__isnull=True, status='published')

        event_type_choices = [{"value": key, "label": label} for key, label in Event.EVENT_TYPE_CHOICES]
        allowed_statuses = ["draft", "pending_approval", "approved"] if is_admin_or_owner else ["draft",
                                                                                                "pending_approval"]
        event_status_choices = [{"value": key, "label": label} for key, label in Event.EVENT_STATUS_CHOICES if
                                key in allowed_statuses]
        who_can_join_choices = [{"value": key, "label": label} for key, label in Event.WHO_CAN_JOIN_CHOICES]
        currency_options = [{"value": "KES", "label": "Kenyan Shilling (KES)"},
                            {"value": "USD", "label": "US Dollar (USD)"}]

        return Response({
            "courses": [{"id": c.id, "title": c.title, "slug": c.slug} for c in courses.order_by("title")],
            "form_options": {
                "event_types": event_type_choices,
                "event_statuses": event_status_choices,
                "who_can_join": who_can_join_choices,
                "currencies": currency_options,
            },
            "defaults": {
                "timezone": "Africa/Nairobi",
                "currency": "KES",
                "event_type": "online",
                "who_can_join": "anyone",
            },
        })

    @action(detail=True, methods=["patch"], url_path='attendees/(?P<registration_id>[^/.]+)')
    def update_attendee(self, request, slug=None, registration_id=None):
        registration = get_object_or_404(EventRegistration, id=registration_id, event__slug=slug)
        serializer = EventRegistrationSerializer(registration, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class EventFilterOptionsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        active_org = getattr(request, "active_organization", None)
        now = timezone.now()

        event_type_data = [
            {"id": value, "label": display} for value, display in Event.EVENT_TYPE_CHOICES
        ]

        if active_org:
            categories = OrgCategory.objects.filter(
                organization=active_org,
                courses__events__isnull=False,
                courses__events__start_time__gte=now,
            ).distinct().order_by("name")
            category_data = [{"id": c.name, "label": c.name} for c in categories]
        else:
            categories = GlobalSubCategory.objects.filter(
                courses__organization__isnull=True,
                courses__events__isnull=False,
                courses__events__start_time__gte=now,
            ).distinct().order_by("name")
            category_data = [{"id": c.slug, "label": c.name} for c in categories]

        price_data = [
            {"id": "all", "label": "All"},
            {"id": "free", "label": "Free"},
            {"id": "paid", "label": "Paid"},
        ]
        upcoming_data = [
            {"id": "all", "label": "All Upcoming"},
            {"id": "next_7_days", "label": "Next 7 Days"},
            {"id": "next_30_days", "label": "Next 30 Days"},
            {"id": "next_90_days", "label": "Next 90 Days"},
            {"id": "this_year", "label": "This Year"},
        ]

        return Response({
            "event_types": event_type_data,
            "categories": category_data,
            "price_options": price_data,
            "upcoming_options": upcoming_data,
        })


class StudentRegisteredEventsViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'slug'

    def get_queryset(self):
        return Event.objects.filter(
            registrations__user=self.request.user,
            registrations__status='registered'
        ).distinct()

    def get_serializer_class(self):
        if self.action == 'list':
            return EventListSerializer
        return EventSerializer

    def list(self, request, *args, **kwargs):
        user = request.user
        now = timezone.now()
        active_slug = request.query_params.get('active_org')
        search_query = request.query_params.get('search', '')

        active_org = None
        if active_slug:
            active_org = Organization.objects.filter(
                slug=active_slug,
                memberships__user=user,
                memberships__is_active=True
            ).first()

        context_query = Q(event__course__organization=active_org) if active_org else Q(
            event__course__organization__isnull=True)

        registrations = EventRegistration.objects.filter(
            user=user,
            status='registered'
        ).filter(context_query).select_related(
            'event', 'event__course'
        ).order_by('event__start_time')

        if search_query:
            registrations = registrations.filter(
                Q(event__title__icontains=search_query) |
                Q(event__course__title__icontains=search_query)
            )

        ongoing, upcoming, past = [], [], []

        for reg in registrations:
            serializer = EventListSerializer(reg.event, context={'request': request})
            event_data = serializer.data
            if reg.event.start_time <= now <= reg.event.end_time:
                ongoing.append(event_data)
            elif reg.event.start_time > now:
                upcoming.append(event_data)
            else:
                past.append(event_data)

        return Response({
            "context": {
                "type": "organization" if active_org else "personal",
                "label": active_org.name if active_org else "Personal Workspace",
            },
            "groups": {"ongoing": ongoing, "upcoming": upcoming, "past": past}
        })

    def retrieve(self, request, *args, **kwargs):
        event = self.get_object()
        serializer = self.get_serializer(event)
        event_data = serializer.data

        now = timezone.now()
        is_ongoing = event.computed_status == 'ongoing'
        activation_time = event.start_time - timedelta(hours=1)

        can_join = (now >= activation_time or is_ongoing) and event.event_type != 'physical'

        event_data['can_join'] = can_join
        event_data['mic_locked'] = getattr(event, 'mic_locked', False)
        event_data['camera_locked'] = getattr(event, 'camera_locked', False)
        event_data['screen_locked'] = getattr(event, 'screen_locked', False)

        event_data['end_time'] = event.end_time.isoformat() if event.end_time else None

        if not can_join:
            event_data['meeting_link'] = None

        return Response(event_data)

    @action(detail=True, methods=["get"])
    def join(self, request, slug=None):
        event = self.get_object()
        user = request.user

        if event.event_type == 'physical':
            return Response({"error": "This is a physical event."}, status=400)

        now = timezone.now()
        is_ongoing = event.computed_status == 'ongoing'
        buffer_time = event.start_time - timedelta(hours=1)

        if event.organizer != user and now < buffer_time and not is_ongoing:
            return Response({
                "error": "too_early",
                "message": "The event room is not yet open.",
                "open_at": buffer_time
            }, status=403)

        is_host = (user == event.organizer)
        token = api.AccessToken(LK_API_KEY, LK_API_SECRET) \
            .with_identity(str(user.id)) \
            .with_name(user.get_full_name() or user.username) \
            .with_grants(api.VideoGrants(
            room_join=True,
            room=event.chat_room_id,
            can_publish=is_host,
            can_subscribe=True,
        ))

        resources_data = [
            {"id": res.id, "title": res.title, "file": request.build_absolute_uri(res.file.url)}
            for res in event.attachments.all()
        ]

        return Response({
            "token": token.to_jwt(),
            "url": LK_SERVER_URL,
            "is_host": is_host,
            "host_identity": str(event.organizer.id),
            "effective_end_datetime": event.end_time.isoformat(),  # Updated time will reflect here
            "resources": resources_data,
            "mic_locked": getattr(event, 'mic_locked', False),
            "camera_locked": getattr(event, 'camera_locked', False),
            "screen_locked": getattr(event, 'screen_locked', False),
            "course_slug": event.course.slug if event.course else None,
            "type": "native" if event.chat_room_id else ("external" if event.meeting_link else "none"),
            "external_url": event.meeting_link if (event.meeting_link and not event.chat_room_id) else None,
            "internal_slug": event.slug
        })

    @action(detail=True, methods=["get"])
    def ticket(self, request, slug=None):
        event = self.get_object()
        if event.event_type == 'online':
            return Response({"error": "Online events do not have tickets."}, status=400)

        reg = get_object_or_404(EventRegistration, event=event, user=request.user, status='registered')
        pdf_buffer = generate_event_ticket_pdf(reg)
        response = HttpResponse(pdf_buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="Ticket_{event.slug}.pdf"'
        return response


