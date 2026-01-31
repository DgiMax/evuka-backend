import json
from datetime import datetime, timedelta
from django.http import HttpResponse
from django.utils import timezone
from django.db.models import Q, Count
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAuthenticatedOrReadOnly
from livekit import api

from courses.models import Course, OrgCategory, GlobalSubCategory
from .models import Event, EventRegistration
from .serializers import (
    EventSerializer,
    EventListSerializer,
    EventRegistrationSerializer,
    TutorEventDetailSerializer,
    CreateEventSerializer,
    FeaturedEventSerializer,
)
from .utils import generate_pdf_ticket

LK_API_KEY = "devkey"
LK_API_SECRET = "SecureLiveKitSecretKey2026EvukaProject"
LK_SERVER_URL = "ws://127.0.0.1:7880"


class BestUpcomingEventView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        active_org = getattr(request, "active_organization", None)
        now = timezone.now()

        base_qs = Event.objects.select_related("course")

        if active_org:
            queryset = base_qs.filter(course__organization=active_org)
        else:
            queryset = base_qs.filter(course__organization__isnull=True)

        queryset = queryset.filter(
            event_status="approved",
            start_time__gt=now,
            who_can_join="anyone",
            registration_open=True
        )

        queryset = queryset.annotate(
            confirmed_registrations=Count(
                "registrations",
                filter=Q(registrations__status__in=["registered", "attended"]),
                distinct=True
            )
        )

        best_event = queryset.order_by("-confirmed_registrations", "start_time").first()

        if not best_event:
            return Response(
                {"detail": "No eligible best upcoming event found."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = FeaturedEventSerializer(best_event, context={'request': request})
        return Response(serializer.data)


class PublicEventViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = EventSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    lookup_field = "slug"

    def get_serializer_class(self):
        if self.action == "list":
            return EventListSerializer
        return EventSerializer

    def get_queryset(self):
        active_org = getattr(self.request, "active_organization", None)
        now = timezone.now()

        base_qs = (
            Event.objects.select_related(
                "course", "organizer",
                "course__global_subcategory", "course__org_category"
            )
            .prefetch_related("agenda", "attachments", "learning_objectives", "rules")
        )

        if active_org:
            queryset = base_qs.filter(course__organization=active_org)
        else:
            queryset = base_qs.filter(course__organization__isnull=True)

        queryset = queryset.filter(
            event_status="approved",
            end_time__gte=now
        )

        event_type = self.request.query_params.get("type")
        category_slug = self.request.query_params.get("category")
        price_option = self.request.query_params.get("price")
        upcoming_option = self.request.query_params.get("upcoming")

        if event_type:
            queryset = queryset.filter(event_type__in=event_type.split(","))

        if category_slug:
            if active_org:
                queryset = queryset.filter(course__org_category__name=category_slug)
            else:
                queryset = queryset.filter(course__global_subcategory__slug=category_slug)

        if price_option == "free":
            queryset = queryset.filter(is_paid=False)
        elif price_option == "paid":
            queryset = queryset.filter(is_paid=True)

        if upcoming_option == "next_7_days":
            queryset = queryset.filter(start_time__range=(now, now + timedelta(days=7)))
        elif upcoming_option == "next_30_days":
            queryset = queryset.filter(start_time__range=(now, now + timedelta(days=30)))

        return queryset.order_by("start_time")

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
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

    @action(detail=True, methods=["get"], permission_classes=[IsAuthenticated])
    def join(self, request, slug=None):
        event = self.get_object()
        user = request.user

        if not EventRegistration.objects.filter(event=event, user=user, status__in=['registered', 'attended']).exists():
            if event.organizer != user:
                return Response({"error": "You are not registered for this event."}, status=403)

        if event.event_type == 'physical':
            return Response({"error": "This is a physical event. Please use your ticket to check in."}, status=400)

        now = timezone.now()
        buffer_time = event.start_time - timedelta(hours=1)

        if event.organizer != user:
            if now < buffer_time:
                minutes_left = int((buffer_time - now).total_seconds() / 60)
                return Response({
                    "error": "too_early",
                    "message": f"The event room will open 1 hour before start time. Please return in {minutes_left} minutes.",
                    "open_at": buffer_time
                }, status=403)

        if event.meeting_link and not event.chat_room_id:
            return Response({"type": "external", "url": event.meeting_link})

        participant_identity = str(user.id)
        participant_name = user.get_full_name() or user.username
        is_host = (user == event.organizer)

        token = api.AccessToken(LK_API_KEY, LK_API_SECRET) \
            .with_identity(participant_identity) \
            .with_name(participant_name) \
            .with_grants(api.VideoGrants(
            room_join=True,
            room=event.chat_room_id,
            can_publish=is_host,
            can_subscribe=True,
        ))

        return Response({
            "type": "native",
            "token": token.to_jwt(),
            "url": LK_SERVER_URL,
            "is_host": is_host
        })

    @action(detail=True, methods=["get"], permission_classes=[IsAuthenticated])
    def ticket(self, request, slug=None):
        event = self.get_object()

        if event.event_type == 'online':
            return Response({"error": "Online events do not require a physical ticket."}, status=400)

        try:
            reg = EventRegistration.objects.get(event=event, user=request.user, status='registered')
        except EventRegistration.DoesNotExist:
            return Response({"error": "No active registration found."}, status=404)

        pdf_buffer = generate_pdf_ticket(reg)

        filename = f"Ticket_{event.slug}_{reg.ticket_id.hex[:6]}.pdf"
        response = HttpResponse(pdf_buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


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
                courses = Course.objects.filter(
                    organization=active_org,
                    status='published'
                )
            else:
                courses = Course.objects.filter(
                    organization=active_org,
                    creator=user,
                    status='published'
                )
        else:
            is_admin_or_owner = False
            courses = Course.objects.filter(
                creator=user,
                organization__isnull=True,
                status='published'
            )

        event_type_choices = [
            {"value": key, "label": label} for key, label in Event.EVENT_TYPE_CHOICES
        ]

        if is_admin_or_owner:
            allowed_statuses = ["draft", "pending_approval", "approved"]
        else:
            allowed_statuses = ["draft", "pending_approval"]

        event_status_choices = [
            {"value": key, "label": label}
            for key, label in Event.EVENT_STATUS_CHOICES
            if key in allowed_statuses
        ]
        who_can_join_choices = [
            {"value": key, "label": label} for key, label in Event.WHO_CAN_JOIN_CHOICES
        ]
        currency_options = [
            {"value": "KES", "label": "Kenyan Shilling (KES)"},
            {"value": "USD", "label": "US Dollar (USD)"},
        ]

        data = {
            "courses": [
                {"id": c.id, "title": c.title, "slug": c.slug}
                for c in courses.order_by("title")
            ],
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
        }
        return Response(data)


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