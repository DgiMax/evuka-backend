from rest_framework import viewsets, permissions, status, generics
from rest_framework.views import APIView
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from django.db.models import Q
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.filters import SearchFilter
from django_filters.rest_framework import DjangoFilterBackend
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from rest_framework.generics import CreateAPIView

# --- External App Imports ---
from orders.models import Order, OrderItem
from payments.models import Payment
from payments.services.paystack import initialize_payment

# --- Local Imports (Organizations App) ---
from .models import Organization, OrgMembership, GuardianLink, OrgCategory, OrgLevel
from .filters import OrganizationFilter
from .permissions import IsOrgMember, IsOrgAdminOrOwner, IsOrgStaff, get_active_org

# Imported from your local serializers.py (which we fixed in the previous step)
from .serializers import (
    OrganizationSerializer, OrgMembershipSerializer, GuardianLinkSerializer,
    OrgLevelSerializer, OrgCategorySerializer, OrganizationCreateSerializer,
    StudentEnrollmentSerializer, OrganizationListSerializer,
    OrganizationDetailSerializer, OrgTeamMemberSerializer,
    OrgAdminInvitationSerializer
)

# --- Org Community Imports ---
from org_community.models import OrgJoinRequest, OrgInvitation
from org_community.serializers import OrgJoinRequestSerializer, OrgInvitationSerializer

User = get_user_model()


class IsModeratorOrSuperAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user.is_authenticated and (user.is_superadmin or user.is_moderator))


class OrganizationViewSet(viewsets.ModelViewSet):
    parser_classes = (MultiPartParser, FormParser, JSONParser)
    serializer_class = OrganizationSerializer
    lookup_field = 'slug'
    filter_backends = [DjangoFilterBackend, SearchFilter]
    search_fields = ['name', 'description']
    filterset_class = OrganizationFilter

    def get_queryset(self):
        queryset = Organization.objects.filter(approved=True)
        if self.request.user.is_authenticated:
            # Users can also see unapproved orgs they belong to (e.g., drafts)
            my_orgs = Organization.objects.filter(memberships__user=self.request.user)
            queryset = (queryset | my_orgs).distinct()

        return queryset

    def get_permissions(self):
        if self.action in ["approve", "reject"]:
            return [IsModeratorOrSuperAdmin()]
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == 'create':
            return OrganizationCreateSerializer
        if self.action == 'list':
            return OrganizationListSerializer
        if self.action in ['retrieve', 'current', 'details_view']:
            return OrganizationDetailSerializer
        return self.serializer_class

    @action(detail=True, methods=['get'], url_path='details')
    def details_view(self, request, slug=None):
        org = self.get_object()
        serializer = self.get_serializer(org)
        return Response(serializer.data)

    @action(detail=False, methods=['get', 'patch'], permission_classes=[permissions.IsAuthenticated])
    def current(self, request):
        slug = request.headers.get("X-Organization-Slug")
        if not slug:
            return Response({"detail": "Organization slug header missing."}, status=400)

        try:
            # We use the base queryset logic to ensure they have access
            org = self.get_queryset().get(slug=slug)
        except Organization.DoesNotExist:
            return Response({"detail": "Organization not found or access denied."}, status=404)

        if request.method == 'GET':
            if not IsOrgMember().has_permission(request, self):
                return Response({"detail": "You are not a member of this organization."}, status=403)
            serializer = self.get_serializer(org)
            return Response(serializer.data)

        elif request.method == 'PATCH':
            request.active_organization = org
            if not IsOrgAdminOrOwner().has_permission(request, self):
                return Response({"detail": "Only Admins can edit organization details."}, status=403)

            serializer = self.get_serializer(org, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)

    @action(detail=True, methods=["post"], permission_classes=[IsModeratorOrSuperAdmin])
    def approve(self, request, slug=None):
        org = self.get_object()
        org.approve()
        return Response({"status": "approved"})

    @action(detail=True, methods=["post"], permission_classes=[IsModeratorOrSuperAdmin])
    def reject(self, request, slug=None):
        org = self.get_object()
        org.reject(delete=False)
        return Response({"status": "rejected"})

    @action(detail=True, methods=['post'], url_path='validate_enrollment',
            permission_classes=[permissions.IsAuthenticated])
    @transaction.atomic
    def validate_enrollment(self, request, slug=None):
        organization = self.get_object()
        user = request.user
        request.data['organization_slug'] = slug

        serializer = StudentEnrollmentSerializer(data=request.data,
                                                 context={'request': request, 'organization': organization})
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data
        org_level = validated_data.get('org_level')
        price = organization.membership_price
        is_paid = price > 0

        membership, _ = OrgMembership.objects.update_or_create(
            user=user, organization=organization,
            defaults={'role': 'student', 'level': org_level, 'is_active': False,
                      'payment_status': 'pending' if is_paid else 'free', 'expires_at': None}
        )

        if not is_paid:
            membership.activate_membership()
            return Response({"detail": f"Successfully enrolled in {organization.name}.", "status": "active",
                             "membership_id": membership.id})

        return Response({
            "detail": f"Proceed to payment for KES {price}.", "status": "payment_required",
            "membership_id": membership.id, "price": price, "org_level_id": org_level.id if org_level else None,
        })

    @action(detail=True, methods=['post'], url_path='initiate_payment',
            permission_classes=[permissions.IsAuthenticated])
    @transaction.atomic
    def initiate_payment(self, request, slug=None):
        organization = self.get_object()
        user = request.user
        membership_id = request.data.get('membership_id')
        payment_method = request.data.get('payment_method')

        if not membership_id:
            return Response({"error": "Membership ID required."}, status=400)

        try:
            membership = OrgMembership.objects.get(id=membership_id, user=user, organization=organization,
                                                   payment_status='pending')
        except OrgMembership.DoesNotExist:
            return Response({"error": "Pending membership not found."}, status=404)

        price = organization.membership_price
        if price <= 0:
            return Response({"detail": "Membership is free."}, status=400)

        order = Order.objects.create(user=user, total_amount=price, status='pending', payment_status='unpaid')
        OrderItem.objects.create(order=order, organization=organization, price=price, quantity=1)

        transaction_payment = Payment.objects.create(
            order=order, user=user, provider="paystack", amount=order.total_amount, currency="KES", status='pending',
            payment_method=payment_method,
            metadata={'organization_id': organization.id, 'user_id': user.id, 'membership_id': membership.id,
                      'org_level_id': membership.level.id if membership.level else None}
        )

        response = initialize_payment(email=user.email, amount=transaction_payment.amount,
                                      reference=transaction_payment.reference_code, method=payment_method)

        if response.get("status"):
            transaction_payment.metadata.update({"authorization_url": response["data"]["authorization_url"],
                                                 "access_code": response["data"]["access_code"]})
            transaction_payment.status = "processing"
            transaction_payment.save()
            return Response({
                "detail": "Redirecting for payment.", "authorization_url": response["data"]["authorization_url"],
                "reference": transaction_payment.reference_code, "order_id": order.id, "payment_method": payment_method
            }, status=202)
        else:
            order.status, transaction_payment.status = 'cancelled', 'failed'
            order.save()
            transaction_payment.save()
            raise Exception(response.get('message', 'Paystack error.'))


class OrgCategoryViewSet(viewsets.ModelViewSet):
    serializer_class = OrgCategorySerializer
    permission_classes = [permissions.IsAuthenticated, IsOrgAdminOrOwner]

    def get_queryset(self):
        return OrgCategory.objects.filter(organization__slug=self.kwargs['organization_slug'])

    def perform_create(self, serializer):
        org = get_object_or_404(Organization, slug=self.kwargs['organization_slug'])
        serializer.save(organization=org)


class OrgLevelViewSet(viewsets.ModelViewSet):
    serializer_class = OrgLevelSerializer
    permission_classes = [permissions.IsAuthenticated, IsOrgAdminOrOwner]

    def get_queryset(self):
        return OrgLevel.objects.filter(organization__slug=self.kwargs['organization_slug']).order_by('order')

    def perform_create(self, serializer):
        org = get_object_or_404(Organization, slug=self.kwargs['organization_slug'])
        serializer.save(organization=org)


class OrgMembershipViewSet(viewsets.ModelViewSet):
    queryset = OrgMembership.objects.all()
    serializer_class = OrgMembershipSerializer
    permission_classes = [permissions.IsAuthenticated]


class GuardianLinkViewSet(viewsets.ModelViewSet):
    serializer_class = GuardianLinkSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        # 1. Base Logic: Users can ALWAYS see links where they are the parent or student
        queryset = GuardianLink.objects.filter(Q(parent=user) | Q(student=user))

        # 2. Admin Logic: If an Admin is viewing their Organization's dashboard
        active_org = get_active_org(self.request)

        if active_org:
            is_admin = OrgMembership.objects.filter(
                user=user,
                organization=active_org,
                role__in=['admin', 'owner'],
                is_active=True
            ).exists()

            if is_admin:
                org_links = GuardianLink.objects.filter(organization=active_org)
                queryset = (queryset | org_links).distinct()

        return queryset


class OrgTeamViewSet(viewsets.ModelViewSet):
    serializer_class = OrgMembershipSerializer
    filter_backends = [SearchFilter]
    search_fields = ['user__username', 'user__email']

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsOrgMember()]
        return [IsOrgAdminOrOwner()]

    def get_queryset(self):
        active_org = getattr(self.request, "active_organization", None)
        if not active_org:
            return OrgMembership.objects.none()
        return OrgMembership.objects.filter(organization=active_org).select_related('user')

    @action(detail=False, methods=['post'])
    def invite(self, request):
        active_org = getattr(self.request, "active_organization", None)
        email = request.data.get('email')
        role = request.data.get('role', 'tutor')
        if not email:
            return Response({"error": "Email is required."}, status=400)

        try:
            user_to_add = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({"error": "User not found."}, status=404)

        if OrgMembership.objects.filter(user=user_to_add, organization=active_org).exists():
            return Response({"error": "User already member."}, status=400)

        if OrgInvitation.objects.filter(invited_user=user_to_add, organization=active_org, status="pending").exists():
            return Response({"error": "Invitation already sent."}, status=400)

        OrgInvitation.objects.create(organization=active_org, invited_by=request.user, invited_user=user_to_add,
                                     role=role, status="pending")
        return Response({"status": f"Invitation sent to {email}."}, status=201)


class ActiveOrganizationView(generics.RetrieveUpdateAPIView):
    serializer_class = OrganizationDetailSerializer
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def get_object(self):
        active_org = getattr(self.request, "active_organization", None)
        if not active_org:
            slug = self.request.headers.get("X-Organization-Slug")
            if slug:
                active_org = get_object_or_404(Organization, slug=slug)
        if not active_org:
            self.permission_denied(self.request, message="No active organization.")
        if self.request.method in ['PUT', 'PATCH']:
            if not IsOrgAdminOrOwner().has_permission(self.request, self):
                self.permission_denied(self.request, message="Only admins can edit.")
        return active_org


class OrganizationCreateView(CreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OrganizationCreateSerializer
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        # FIX: We rely on the Serializer to create the Org AND the initial Owner Membership
        # This prevents the 'IntegrityError' of trying to add the owner twice.
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization = serializer.save()

        # NOTE: OrgMembership creation removed here because OrganizationCreateSerializer handles it.

        # We manually use the OrganizationSerializer for the response
        # to ensure any 'logo' URL is formatted correctly as absolute.
        response_serializer = OrganizationSerializer(organization, context={'request': request})
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class OrgJoinRequestViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Handles listing and approving join requests.
    Note: Ideally, these models should be managed in the 'org_community' app views,
    but they are included here if you prefer a single 'organization' view file.
    """
    serializer_class = OrgJoinRequestSerializer
    permission_classes = [IsOrgStaff]

    def get_queryset(self):
        active_org = getattr(self.request, "active_organization", None)
        if not active_org:
            slug = self.request.headers.get("X-Organization-Slug")
            if slug:
                try:
                    active_org = Organization.objects.get(slug=slug)
                    self.request.active_organization = active_org
                except Organization.DoesNotExist:
                    pass
        if not active_org:
            return OrgJoinRequest.objects.none()
        return OrgJoinRequest.objects.filter(organization=active_org, status="pending").select_related('user')

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def approve(self, request, pk=None):
        req = self.get_object()
        if req.status != 'pending':
            return Response({"error": "Not pending."}, status=400)

        if OrgMembership.objects.filter(user=req.user, organization=req.organization).exists():
            req.status = 'approved'
            req.save()
            return Response({"error": "Already member."}, status=400)

        OrgMembership.objects.create(user=req.user, organization=req.organization, role='tutor', is_active=True)
        req.status = 'approved'
        req.save()

        # Auto-reject any pending invitations if the request is approved
        OrgInvitation.objects.filter(invited_user=req.user, organization=req.organization, status='pending').update(
            status='rejected')
        return Response({"status": "Approved."})

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        req = self.get_object()
        req.status = 'rejected'
        req.save()
        return Response({"status": "Rejected."})


class OrgSentInvitationsViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrgAdminInvitationSerializer
    permission_classes = [IsOrgStaff]

    def get_queryset(self):
        active_org = getattr(self.request, "active_organization", None)
        if not active_org:
            slug = self.request.headers.get("X-Organization-Slug")
            if slug:
                try:
                    active_org = Organization.objects.get(slug=slug)
                    self.request.active_organization = active_org
                except Organization.DoesNotExist:
                    pass
        if not active_org:
            return OrgInvitation.objects.none()
        return OrgInvitation.objects.filter(organization=active_org, status="pending").select_related('invited_user',
                                                                                                      'invited_by')

    @action(detail=True, methods=['post'])
    def revoke(self, request, pk=None):
        inv = self.get_object()
        inv.delete()
        return Response({"status": "Revoked."})


class PublicOrgLevelListView(generics.ListAPIView):
    serializer_class = OrgLevelSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        slug = self.kwargs['slug']
        organization = get_object_or_404(Organization.objects.filter(approved=True), slug=slug)
        return OrgLevel.objects.filter(organization=organization).order_by('order')


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def check_organization_access(request, slug):
    try:
        org = Organization.objects.get(slug=slug, approved=True)
    except Organization.DoesNotExist:
        return Response({'organization_exists': False}, status=404)

    is_member = False
    if request.user.is_authenticated:
        is_member = OrgMembership.objects.filter(user=request.user, organization=org, is_active=True).exists()

    return Response(
        {'is_authenticated': request.user.is_authenticated, 'is_member': is_member, 'organization_exists': True,
         'organization_slug': slug}, status=200)


class OrganizationTeamView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, slug=None):
        active_org = getattr(request, "active_organization", None)
        if not active_org and slug:
            active_org = get_object_or_404(Organization, slug=slug)
        if not active_org:
            return Response({"detail": "Not found."}, status=404)

        memberships = OrgMembership.objects.filter(
            organization=active_org,
            is_active=True,
            role__in=['owner', 'admin', 'tutor']
        ).select_related('user', 'user__creator_profile').prefetch_related('subjects')

        # IMPORTANT: Passing context here ensures images in the nested TeamMemberProfileSerializer are absolute URLs
        serializer = OrgTeamMemberSerializer(memberships, many=True, context={'request': request})

        management = [m for m in serializer.data if m['role'] in ['owner', 'admin']]
        tutors = [m for m in serializer.data if m['role'] == 'tutor']

        return Response({"management": management, "tutors": tutors}, status=200)