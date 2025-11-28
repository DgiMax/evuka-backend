# announcements/permissions.py
from rest_framework import permissions
from organizations.models import OrgMembership


class IsActiveOrgAdminOrOwner(permissions.BasePermission):
    """
    Allows access only to users who are an Admin or Owner
    of the *active* organization in the request.
    """
    message = "You must be an Admin or Owner of this organization to perform this action."

    def has_permission(self, request, view):
        active_org = getattr(request, "active_organization", None)
        if not active_org:
            return False

        try:
            membership = OrgMembership.objects.get(
                user=request.user,
                organization=active_org
            )
            return membership.is_admin_or_owner()
        except OrgMembership.DoesNotExist:
            return False