# organizations/permissions.py
from rest_framework import permissions

class IsOrgMember(permissions.BasePermission):
    """Allows access to any active member of the organization."""
    def has_permission(self, request, view):
        active_org = getattr(request, "active_organization", None)
        if not active_org or not request.user.is_authenticated:
            return False
        return request.user.memberships.filter(organization=active_org, is_active=True).exists()

class IsOrgAdminOrOwner(permissions.BasePermission):
    """Allows write access only to Admins and Owners of the active organization."""
    def has_permission(self, request, view):
        active_org = getattr(request, "active_organization", None)
        if not active_org or not request.user.is_authenticated:
            return False
        return request.user.memberships.filter(
            organization=active_org,
            role__in=['admin', 'owner'],
            is_active=True
        ).exists()