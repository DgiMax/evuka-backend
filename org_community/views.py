from rest_framework import viewsets, permissions, status, generics
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db import transaction
from rest_framework import serializers
from django.contrib.auth import get_user_model
from rest_framework.filters import SearchFilter
from django.shortcuts import get_object_or_404

from organizations.models import Organization, OrgMembership
from organizations.models_finance import TutorAgreement
from organizations.permissions import IsOrgAdminOrOwner, IsOrgStaff

from .models import OrgJoinRequest, AdvancedOrgInvitation, NegotiationLog
from .serializers import (
    OrgDiscoverySerializer,
    OrgJoinRequestCreateSerializer,
    OrgJoinRequestSerializer,
    AdvancedInvitationSerializer,
    InviteActionSerializer
)

User = get_user_model()


class OrganizationDiscoveryViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.AllowAny]
    serializer_class = OrgDiscoverySerializer
    queryset = Organization.objects.filter(approved=True)
    filter_backends = [SearchFilter]
    search_fields = ['name', 'description']

    def get_serializer_context(self):
        return {'request': self.request}


class RequestToJoinView(generics.CreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OrgJoinRequestCreateSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class OrgJoinRequestViewSet(viewsets.ModelViewSet):
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

        return OrgJoinRequest.objects.filter(
            organization=active_org,
            status="pending"
        ).select_related('user')

    @action(detail=True, methods=['post'], permission_classes=[IsOrgAdminOrOwner])
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
            role=req.desired_role,
            is_active=True
        )

        if req.desired_role == 'tutor':
            TutorAgreement.objects.create(
                organization=req.organization,
                user=req.user,
                commission_percent=req.proposed_commission,
                is_active=True,
                signed_by_user=True
            )

        req.status = 'approved'
        req.save()

        AdvancedOrgInvitation.objects.filter(
            email=req.user.email,
            organization=req.organization
        ).delete()

        return Response({"status": f"Request approved. User added as {req.desired_role}."})

    @action(detail=True, methods=['post'], permission_classes=[IsOrgAdminOrOwner])
    def reject(self, request, pk=None):
        req = self.get_object()
        if req.status != 'pending':
            return Response({"error": "Request not pending."}, status=status.HTTP_400_BAD_REQUEST)

        req.status = 'rejected'
        req.save()
        return Response({"status": "Request rejected."})


class OrgSentInvitationsViewSet(viewsets.ModelViewSet):
    serializer_class = AdvancedInvitationSerializer
    permission_classes = [IsOrgAdminOrOwner]

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
            return AdvancedOrgInvitation.objects.none()

        return AdvancedOrgInvitation.objects.filter(
            organization=active_org
        ).order_by('-created_at')

    @action(detail=True, methods=['post'])
    def revoke(self, request, pk=None):
        inv = self.get_object()
        inv.delete()
        return Response({"status": "Invitation revoked."})


class InvitationViewSet(viewsets.ModelViewSet):
    serializer_class = AdvancedInvitationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return AdvancedOrgInvitation.objects.filter(
            email=user.email
        ) | AdvancedOrgInvitation.objects.filter(
            invited_by=user
        )

    def perform_create(self, serializer):
        active_org = getattr(self.request, "active_organization", None)
        if not active_org:
            slug = self.request.headers.get("X-Organization-Slug")
            if slug:
                active_org = get_object_or_404(Organization, slug=slug)

        if not active_org:
            raise serializers.ValidationError({"detail": "Active organization context required."})

        if not IsOrgAdminOrOwner().has_permission(self.request, self):
            raise serializers.ValidationError({"detail": "Only admins can send invitations."})

        serializer.save(organization=active_org, invited_by=self.request.user)

    @action(detail=True, methods=['post'])
    def respond(self, request, pk=None):
        invite = self.get_object()
        serializer = InviteActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        section = data['section']
        act = data['action']

        if invite.email != request.user.email:
            return Response({"error": "Not your invitation."}, status=403)

        with transaction.atomic():
            if section == 'teaching':
                if not invite.is_tutor_invite:
                    return Response({"error": "No teaching offer to respond to."}, status=400)

                if act == 'accept':
                    if invite.tutor_commission < 10:
                        return Response({"error": "Cannot accept. Commission below 10% limit."}, status=400)

                    invite.tutor_status = 'accepted'

                    TutorAgreement.objects.update_or_create(
                        organization=invite.organization,
                        user=request.user,
                        defaults={
                            'commission_percent': invite.tutor_commission,
                            'signed_by_user': True,
                            'is_active': True
                        }
                    )

                elif act == 'reject':
                    invite.tutor_status = 'rejected'

                elif act == 'counter':
                    new_val = data['counter_value']
                    NegotiationLog.objects.create(
                        invitation=invite, actor=request.user,
                        action="Countered Teaching Offer",
                        previous_value=str(invite.tutor_commission),
                        new_value=str(new_val),
                        note=data.get('note', '')
                    )
                    invite.tutor_commission = new_val
                    invite.tutor_status = 'negotiating'

            elif section == 'governance':
                if act == 'accept':
                    invite.gov_status = 'accepted'

                    OrgMembership.objects.update_or_create(
                        organization=invite.organization,
                        user=request.user,
                        defaults={
                            'role': invite.gov_role,
                            'is_active': True
                        }
                    )

                elif act == 'reject':
                    invite.gov_status = 'rejected'

            invite.save()

            if invite.is_fully_resolved:
                OrgJoinRequest.objects.filter(
                    user=request.user,
                    organization=invite.organization,
                    status='pending'
                ).update(status='rejected')

        return Response(self.get_serializer(invite).data)