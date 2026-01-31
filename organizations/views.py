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

from orders.models import Order, OrderItem
from payments.models import Payment
from payments.services.paystack import initialize_transaction

from .models import Organization, OrgMembership, GuardianLink, OrgCategory, OrgLevel
from .filters import OrganizationFilter
from .permissions import IsOrgMember, IsOrgAdminOrOwner, get_active_org

from .serializers import (
    OrganizationSerializer, OrgMembershipSerializer, GuardianLinkSerializer,
    OrgLevelSerializer, OrgCategorySerializer, OrganizationCreateSerializer,
    StudentEnrollmentSerializer, OrganizationListSerializer,
    OrganizationDetailSerializer, OrgTeamMemberSerializer
)

# Note: We do NOT import OrgInvitation/OrgJoinRequest here anymore.
# Those are handled exclusively in the 'org_community' app to prevent circular deps and logic duplication.

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
            my_orgs = Organization.objects.filter(memberships__user=self.request.user)
            queryset = (queryset | my_orgs).distinct()

        return queryset

    def get_permissions(self):
        if self.action in ["approve", "reject"]:
            return [IsModeratorOrSuperAdmin()]
        if self.action == 'create':
            return [permissions.IsAuthenticated()]
        if self.action in ['update', 'partial_update', 'destroy']:
            return [permissions.IsAuthenticated(), IsOrgAdminOrOwner()]
        if self.action in ['list', 'retrieve', 'details_view']:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == 'create':
            return OrganizationCreateSerializer
        if self.action == 'list':
            return OrganizationListSerializer
        if self.action in ['retrieve', 'current', 'details_view', 'update', 'partial_update']:
            return OrganizationDetailSerializer
        return self.serializer_class

    def perform_destroy(self, instance):
        instance.delete()

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
        org.status = 'approved'
        org.save()
        return Response({"status": "approved"})

    @action(detail=True, methods=["post"], permission_classes=[IsModeratorOrSuperAdmin])
    def reject(self, request, slug=None):
        org = self.get_object()
        org.status = 'suspended'
        org.save()
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

        response = initialize_transaction(email=user.email, amount=transaction_payment.amount,
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
        queryset = GuardianLink.objects.filter(Q(parent=user) | Q(student=user))
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

        allowed_roles = ['owner', 'admin', 'tutor']
        return OrgMembership.objects.filter(
            organization=active_org,
            role__in=allowed_roles
        ).select_related('user')


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
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization = serializer.save()
        response_serializer = OrganizationSerializer(organization, context={'request': request})
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


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

        serializer = OrgTeamMemberSerializer(memberships, many=True, context={'request': request})

        management = [m for m in serializer.data if m['role'] in ['owner', 'admin']]
        tutors = [m for m in serializer.data if m['role'] == 'tutor']

        return Response({"management": management, "tutors": tutors}, status=200)


class ValidateOrgContextView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, slug):
        org = Organization.objects.filter(slug=slug).first()

        if not org:
            return Response({
                "error": "not_found",
                "message": "This organization does not exist."
            }, status=status.HTTP_404_NOT_FOUND)

        membership = OrgMembership.objects.filter(
            user=request.user,
            organization=org
        ).first()

        if not membership:
            return Response({
                "error": "no_membership",
                "message": "You are not a member of this organization."
            }, status=status.HTTP_403_FORBIDDEN)

        if org.status == 'draft' and membership.role == 'student':
            return Response({
                "error": "draft_mode",
                "message": f"{org.name} is currently in draft mode and not yet published.",
                "org_name": org.name
            }, status=status.HTTP_403_FORBIDDEN)

        is_draft = org.status == 'draft'

        return Response({
            "status": "success",
            "org_name": org.name,
            "role": membership.role,
            "is_active": membership.is_active,
            "org_status": org.status,
            "is_draft": is_draft
        }, status=status.HTTP_200_OK)