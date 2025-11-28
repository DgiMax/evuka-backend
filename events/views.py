from datetime import timedelta
from django.utils import timezone
from django.db.models import Q, Count

from rest_framework import viewsets, permissions, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import get_object_or_404
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAuthenticatedOrReadOnly

from courses.models import Course, OrgCategory, GlobalSubCategory
from organizations.models import Organization
from .models import Event, EventRegistration
from .serializers import (
    EventSerializer,
    EventListSerializer,
    EventRegistrationSerializer,
    TutorEventDetailSerializer, CreateEventSerializer, FeaturedEventSerializer,
)

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
    """
    Handles all PUBLIC-FACING event logic.
    STRICTLY limits results to future/ongoing events only.
    """
    serializer_class = EventSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    lookup_field = "slug"

    def get_serializer_class(self):
        """Use lightweight serializer for list view."""
        if self.action == "list":
            return EventListSerializer
        return EventSerializer

    def get_queryset(self):
        """
        Context-aware queryset filtering.
        STRICT: Only shows events where end_time >= now.
        """
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


class TutorEventViewSet(viewsets.ModelViewSet):
    """
    A complete ViewSet for Tutors/Admins to manage their events.
    Handles:
    - List (GET /tutor/events/) -> "My Events" page
    - Create (POST /tutor/events/)
    - Retrieve (GET /tutor/events/<slug>/) -> Preview/Edit page
    - Update (PUT /tutor/events/<slug>/)
    - Delete (DELETE /tutor/events/<slug>/)
    - Attendees (GET /tutor/events/<slug>/attendees/)
    - Form Options (GET /tutor/events/form_options/)
    """
    permission_classes = [IsAuthenticated]
    lookup_field = "slug"

    def get_serializer_class(self):
        """Use the correct serializer for the action."""
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
        """
        Returns events owned by the tutor or manageable by them (if org admin).
        This powers the "My Events" page and handles search/filter.
        """
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
        """Copied from EventCreateView"""
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
        """Copied from EventRetrieveUpdateView"""
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
        """Allows organizer or org admins to view attendees."""
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
        """
        Returns context-aware course options and event form dropdown options.
        MERGED from EventFormOptionsView.
        """
        user = request.user
        active_org = getattr(request, "active_organization", None)

        if active_org:
            membership = user.memberships.filter(
                organization=active_org, is_active=True
            ).first()
            is_admin_or_owner = membership and membership.role in ["admin", "owner"]

            if is_admin_or_owner:
                courses = Course.objects.filter(organization=active_org)
            else:
                courses = Course.objects.filter(organization=active_org, creator=user)
        else:
            is_admin_or_owner = False
            courses = Course.objects.filter(creator=user, organization__isnull=True)

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
    """
    Returns filter options for the PUBLIC event list sidebar.
    This view is unchanged and still needed.
    """
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