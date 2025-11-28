from rest_framework import viewsets, permissions, status, generics
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db import transaction
from django.contrib.auth import get_user_model
from rest_framework.filters import SearchFilter

from organizations.models import Organization, OrgMembership
from organizations.permissions import IsOrgAdminOrOwner
from organizations.serializers import OrgUserSerializer

from .models import OrgJoinRequest, OrgInvitation
from .serializers import (
    OrgDiscoverySerializer,
    OrgJoinRequestCreateSerializer,
    OrgJoinRequestSerializer,
    OrgInvitationSerializer,
    UserJoinRequestSerializer
)

User = get_user_model()


class OrganizationDiscoveryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Public API endpoint to list and search for approved organizations.
    Anonymous users can browse, authenticated users see extra context.
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = OrgDiscoverySerializer
    queryset = Organization.objects.filter(approved=True)
    filter_backends = [SearchFilter]
    search_fields = ['name', 'description']

    def get_serializer_context(self):
        return {'request': self.request}


class RequestToJoinView(generics.CreateAPIView):
    """
    Authenticated users can POST here to request to join an org.
    e.g., POST /community/api/request-join/
         {"organization": "org-slug", "message": "I'm a tutor"}
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OrgJoinRequestCreateSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class OrgJoinRequestViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Admins can list, approve, or reject pending join requests.
    This ViewSet is context-aware via the X-Organization-Slug header.
    """
    serializer_class = OrgJoinRequestSerializer
    permission_classes = [IsOrgAdminOrOwner]

    def get_queryset(self):
        active_org = getattr(self.request, "active_organization", None)
        if not active_org:
            return OrgJoinRequest.objects.none()

        return OrgJoinRequest.objects.filter(
            organization=active_org,
            status="pending"
        ).select_related('user')

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


class UserInvitationsViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Authenticated users can list, accept, or reject their PENDING invitations.
    This is for the user's personal "My Invitations" page/section.
    """
    serializer_class = OrgInvitationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return OrgInvitation.objects.filter(
            invited_user=self.request.user,
            status="pending"
        ).select_related('organization', 'invited_by__creator_profile')

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def accept(self, request, pk=None):
        """
        Accept an invitation. This creates the OrgMembership.
        """
        inv = self.get_object()

        if OrgMembership.objects.filter(user=inv.invited_user, organization=inv.organization).exists():
            inv.status = 'accepted'
            inv.save()
            return Response({"error": "You are already a member of this organization."},
                            status=status.HTTP_400_BAD_REQUEST)

        OrgMembership.objects.create(
            user=inv.invited_user,
            organization=inv.organization,
            role=inv.role,
            is_active=True
        )

        inv.status = 'accepted'
        inv.save()

        OrgJoinRequest.objects.filter(
            user=inv.invited_user,
            organization=inv.organization,
            status='pending'
        ).update(status='rejected')

        return Response({"status": "Invitation accepted! Welcome to the team."})

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """
        Reject an invitation.
        """
        inv = self.get_object()
        inv.status = 'rejected'
        inv.save()
        return Response({"status": "Invitation rejected."})


class UserJoinRequestViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Authenticated users can list and cancel their *own* pending join requests.
    This is for the user's personal "My Requests" page/section.
    """
    serializer_class = UserJoinRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return OrgJoinRequest.objects.filter(
            user=self.request.user,
            status="pending"
        ).select_related('organization')

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """
        Allows a user to cancel (delete) their own pending join request.
        """
        req = self.get_object()

        if req.status != 'pending':
            return Response({"error": "This request is no longer pending."}, status=status.HTTP_400_BAD_REQUEST)

        req.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)