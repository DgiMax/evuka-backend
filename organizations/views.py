import requests
from rest_framework.views import APIView
from django.db import transaction
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from rest_framework.permissions import IsAuthenticated
from rest_framework.generics import CreateAPIView
from rest_framework import viewsets, permissions, status, mixins, generics
from rest_framework.decorators import action
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.filters import SearchFilter
from django_filters.rest_framework import DjangoFilterBackend

from orders.models import Order, OrderItem
from payments.models import Payment
from payments.services.paystack import initialize_payment
from org_community.models import OrgJoinRequest, OrgInvitation
from org_community.serializers import OrgJoinRequestSerializer
from .filters import OrganizationFilter
from .models import Organization, OrgMembership, GuardianLink, OrgCategory, OrgLevel
from .serializers import (
    OrganizationSerializer, OrgMembershipSerializer, GuardianLinkSerializer,
    OrgLevelSerializer, OrgCategorySerializer, OrganizationCreateSerializer,
    OrgAdminInvitationSerializer, StudentEnrollmentSerializer, OrganizationListSerializer,
    OrganizationDetailSerializer, OrgTeamMemberSerializer
)
from .permissions import IsOrgMember, IsOrgAdminOrOwner

User = get_user_model()


class IsModeratorOrSuperAdmin(permissions.BasePermission):
    """Custom permission: only moderators/superadmins can approve/reject organizations"""

    def has_permission(self, request, view):
        user = request.user
        return bool(user.is_authenticated and (user.is_superadmin or user.is_moderator))


class OrganizationViewSet(viewsets.ModelViewSet):
    """
    Handles Organization CRUD, Admin approvals, Student discovery (LIST/RETRIEVE),
    and the two-step Enrollment process.
    """
    queryset = Organization.objects.filter(approved=True)
    serializer_class = OrganizationSerializer
    lookup_field = 'slug'
    filter_backends = [DjangoFilterBackend, SearchFilter]
    search_fields = ['name', 'description']
    filterset_class = OrganizationFilter

    def get_permissions(self):
        if self.action in ["approve", "reject"]:
            return [IsModeratorOrSuperAdmin()]
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == 'list':
            return OrganizationListSerializer
        if self.action == 'retrieve':
            return OrganizationDetailSerializer
        return self.serializer_class

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
        """
        Validates level selection and creates a PENDING OrgMembership record.
        Activates membership directly if free.
        """
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

        membership, created = OrgMembership.objects.update_or_create(
            user=user,
            organization=organization,
            defaults={
                'role': 'student',
                'level': org_level,
                'is_active': False,
                'payment_status': 'pending' if is_paid else 'free',
                'expires_at': None,
            }
        )

        if not is_paid:
            membership.activate_membership()
            return Response(
                {"detail": f"Successfully enrolled in {organization.name} (Free Access).",
                 "status": "active",
                 "membership_id": membership.id},
                status=status.HTTP_200_OK
            )

        return Response({
            "detail": f"Paid enrollment validated. Proceed to payment for KES {price}.",
            "status": "payment_required",
            "membership_id": membership.id,
            "price": price,
            "org_level_id": org_level.id if org_level else None,
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='initiate_payment',
            permission_classes=[permissions.IsAuthenticated])
    @transaction.atomic
    def initiate_payment(self, request, slug=None):
        """
        Receives membership ID and payment channel, creates order/payment, and calls Paystack.
        """
        organization = self.get_object()
        user = request.user

        membership_id = request.data.get('membership_id')
        payment_method = request.data.get('payment_method')

        if not membership_id:
            return Response({"error": "Membership ID is required to initiate payment."},
                            status=status.HTTP_400_BAD_REQUEST)

        VALID_METHODS = ['card', 'mobile_money_mpesa', 'bank_transfer', 'ussd']
        if payment_method not in VALID_METHODS:
            return Response({"error": f"Invalid payment method selected. Must be one of: {', '.join(VALID_METHODS)}."},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            membership = OrgMembership.objects.get(
                id=membership_id,
                user=user,
                organization=organization,
                payment_status='pending'
            )
        except OrgMembership.DoesNotExist:
            return Response({"error": "Pending membership record not found or invalid."},
                            status=status.HTTP_404_NOT_FOUND)

        price = organization.membership_price
        if price <= 0:
            return Response({"detail": "Error: Membership is free, no payment needed."},
                            status=status.HTTP_400_BAD_REQUEST)

        order = Order.objects.create(
            user=user,
            total_amount=price,
            status='pending',
            payment_status='unpaid'
        )

        OrderItem.objects.create(
            order=order,
            organization=organization,
            price=price,
            quantity=1
        )

        transaction_payment = Payment.objects.create(
            order=order,
            user=user,
            provider="paystack",
            amount=order.total_amount,
            currency="KES",
            status='pending',
            payment_method=payment_method,
            metadata={
                'organization_id': organization.id,
                'user_id': user.id,
                'membership_id': membership.id,
                'org_level_id': membership.level.id if membership.level else None,
            }
        )

        payment_reference = transaction_payment.reference_code

        response = initialize_payment(
            email=user.email,
            amount=transaction_payment.amount,
            reference=payment_reference,
            method=payment_method,
        )

        if response.get("status"):
            transaction_payment.metadata.update({
                "authorization_url": response["data"]["authorization_url"],
                "access_code": response["data"]["access_code"],
            })
            transaction_payment.status = "processing"
            transaction_payment.save()

            return Response({
                "detail": f"Redirecting for payment of KES {price} via {payment_method}.",
                "authorization_url": response["data"]["authorization_url"],
                "reference": payment_reference,
                "order_id": order.id,
                "payment_method": payment_method
            }, status=status.HTTP_202_ACCEPTED)
        else:
            order.status = 'cancelled'
            order.save()
            transaction_payment.status = 'failed'
            transaction_payment.save()
            raise Exception(response.get('message', 'Paystack initialization error.'))


class OrgMembershipViewSet(viewsets.ModelViewSet):
    queryset = OrgMembership.objects.all()
    serializer_class = OrgMembershipSerializer
    permission_classes = [permissions.IsAuthenticated]


class GuardianLinkViewSet(viewsets.ModelViewSet):
    queryset = GuardianLink.objects.all()
    serializer_class = GuardianLinkSerializer
    permission_classes = [permissions.IsAuthenticated]


class OrgTeamViewSet(viewsets.ModelViewSet):
    serializer_class = OrgMembershipSerializer
    filter_backends = [SearchFilter]
    search_fields = ['user__username', 'user__email', 'user__first_name', 'user__last_name']

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
            return Response({"error": "Email is required."}, status=status.HTTP_400_BAD_REQUEST)
        valid_roles = [r[0] for r in OrgMembership.ROLE_CHOICES]
        if role not in valid_roles:
            return Response({"error": f"Invalid role '{role}'."}, status=status.HTTP_400_BAD_REQUEST)
        if role == 'owner':
            return Response({"error": "Cannot invite a user as 'owner'."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            user_to_add = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({"error": "User not found on platform. Ask them to register first."},
                            status=status.HTTP_404_NOT_FOUND)
        if OrgMembership.objects.filter(user=user_to_add, organization=active_org).exists():
            return Response({"error": "User is already a member of this organization."},
                            status=status.HTTP_400_BAD_REQUEST)
        if OrgInvitation.objects.filter(invited_user=user_to_add, organization=active_org, status="pending").exists():
            return Response({"error": "An invitation has already been sent to this user."},
                            status=status.HTTP_400_BAD_REQUEST)
        OrgInvitation.objects.create(
            organization=active_org,
            invited_by=request.user,
            invited_user=user_to_add,
            role=role,
            status="pending"
        )
        return Response({"status": f"Invitation sent to {user_to_add.email} for role '{role}'."},
                        status=status.HTTP_201_CREATED)


class ActiveOrganizationView(generics.RetrieveUpdateAPIView):
    serializer_class = OrganizationDetailSerializer
    permission_classes = [IsAuthenticated, IsOrgMember]

    def get_object(self):
        active_org = getattr(self.request, "active_organization", None)
        if not active_org:
            self.permission_denied(self.request, message="No active organization.")
        if self.request.method in ['PUT', 'PATCH']:
            if not IsOrgAdminOrOwner().has_permission(self.request, self):
                self.permission_denied(self.request, message="Only admins can edit organization details.")
        return active_org


class OrgCategoryViewSet(viewsets.ModelViewSet):
    serializer_class = OrgCategorySerializer
    permission_classes = [IsAuthenticated, IsOrgAdminOrOwner]

    def get_queryset(self):
        active_org = getattr(self.request, "active_organization", None)
        if not active_org: return OrgCategory.objects.none()
        return OrgCategory.objects.filter(organization=active_org)

    def perform_create(self, serializer):
        active_org = getattr(self.request, "active_organization", None)
        serializer.save(organization=active_org)


class OrgLevelViewSet(viewsets.ModelViewSet):
    serializer_class = OrgLevelSerializer
    permission_classes = [IsAuthenticated, IsOrgAdminOrOwner]

    def get_queryset(self):
        active_org = getattr(self.request, "active_organization", None)
        if not active_org: return OrgLevel.objects.none()
        return OrgLevel.objects.filter(organization=active_org).order_by('order')

    def perform_create(self, serializer):
        active_org = getattr(self.request, "active_organization", None)
        serializer.save(organization=active_org)


class OrganizationCreateView(CreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = OrganizationCreateSerializer

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization = serializer.save()
        OrgMembership.objects.create(
            user=request.user,
            organization=organization,
            role='owner',
            is_active=True
        )
        return_data = OrganizationSerializer(organization).data
        headers = self.get_success_headers(return_data)
        return Response(return_data, status=status.HTTP_201_CREATED, headers=headers)


class OrgJoinRequestViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrgJoinRequestSerializer
    permission_classes = [IsOrgAdminOrOwner]

    def get_queryset(self):
        active_org = getattr(self.request, "active_organization", None)
        if not active_org:
            return OrgJoinRequest.objects.none()
        return OrgJoinRequest.objects.filter(organization=active_org, status="pending").select_related('user')

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def approve(self, request, pk=None):
        req = self.get_object()
        if req.status != 'pending':
            return Response({"error": "Request not pending."}, status=status.HTTP_400_BAD_REQUEST)
        if OrgMembership.objects.filter(user=req.user, organization=req.organization).exists():
            req.status = 'approved'
            req.save()
            return Response({"error": "User is already a member."}, status=status.HTTP_400_BAD_REQUEST)
        OrgMembership.objects.create(
            user=req.user,
            organization=req.organization,
            role='tutor',
            is_active=True
        )
        req.status = 'approved'
        req.save()
        OrgInvitation.objects.filter(
            invited_user=req.user,
            organization=req.organization,
            status='pending'
        ).update(status='rejected')
        return Response({"status": "Request approved, user added as tutor."})

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        req = self.get_object()
        if req.status != 'pending':
            return Response({"error": "Request not pending."}, status=status.HTTP_400_BAD_REQUEST)
        req.status = 'rejected'
        req.save()
        return Response({"status": "Request rejected."})


class OrgSentInvitationsViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrgAdminInvitationSerializer
    permission_classes = [IsOrgAdminOrOwner]

    def get_queryset(self):
        active_org = getattr(self.request, "active_organization", None)
        if not active_org:
            return OrgInvitation.objects.none()
        return OrgInvitation.objects.filter(
            organization=active_org,
            status="pending"
        ).select_related('invited_user', 'invited_by')

    @action(detail=True, methods=['post'])
    def revoke(self, request, pk=None):
        inv = self.get_object()
        if inv.status != 'pending':
            return Response({"error": "This invitation is no longer pending."}, status=status.HTTP_400_BAD_REQUEST)
        inv.delete()
        return Response({"status": "Invitation revoked."}, status=204)


class OrganizationRetrieveView(generics.RetrieveAPIView):
    serializer_class = OrganizationDetailSerializer
    permission_classes = [IsOrgMember | permissions.IsAuthenticated]
    lookup_field = 'slug'
    queryset = Organization.objects.filter(approved=True)


class PublicOrgLevelListView(generics.ListAPIView):
    serializer_class = OrgLevelSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        slug = self.kwargs['slug']
        organization = get_object_or_404(Organization.objects.filter(approved=True), slug=slug)
        return OrgLevel.objects.filter(organization=organization).order_by('order')


@api_view(['GET'])
@permission_classes([AllowAny])
def check_organization_access(request, slug):
    try:
        org = Organization.objects.get(slug=slug, approved=True)
    except Organization.DoesNotExist:
        return Response({'organization_exists': False}, status=status.HTTP_404_NOT_FOUND)

    is_authenticated = request.user.is_authenticated
    is_member = False

    if is_authenticated:
        is_member = OrgMembership.objects.filter(
            user=request.user,
            organization=org,
            is_active=True
        ).exists()

    return Response({
        'is_authenticated': is_authenticated,
        'is_member': is_member,
        'organization_exists': True,
        'organization_slug': slug
    }, status=status.HTTP_200_OK)


class OrganizationTeamView(APIView):
    """
    Returns a grouped list of organization members (Management & Tutors).
    Context-aware: Checks request.active_organization first, then URL slug.
    """
    permission_classes = [AllowAny]

    def get(self, request, slug=None):
        active_org = getattr(request, "active_organization", None)

        if not active_org and slug:
            active_org = get_object_or_404(Organization, slug=slug)

        if not active_org:
            return Response(
                {"detail": "Organization not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        memberships = OrgMembership.objects.filter(
            organization=active_org,
            is_active=True,
            role__in=['owner', 'admin', 'tutor']
        ).select_related(
            'user',
            'user__creator_profile'
        ).prefetch_related('subjects')

        management = []
        tutors = []

        serializer = OrgTeamMemberSerializer(memberships, many=True, context={'request': request})

        for member_data in serializer.data:
            role = member_data['role']
            if role in ['owner', 'admin']:
                management.append(member_data)
            elif role == 'tutor':
                tutors.append(member_data)

        return Response({
            "management": management,
            "tutors": tutors
        }, status=status.HTTP_200_OK)