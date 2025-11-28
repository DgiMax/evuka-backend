from rest_framework import permissions
from organizations.models import OrgMembership


class IsTutorOrOrgAdmin(permissions.BasePermission):
    """
    Allows access if user is a tutor of the course or an admin/owner in the active organization.
    """

    def has_permission(self, request, view):
        user = request.user
        active_org = getattr(request, "active_organization", None)

        if not user.is_authenticated:
            return False

        if active_org:
            membership = OrgMembership.objects.filter(
                user=user, organization=active_org
            ).first()
            return membership and membership.role in ["admin", "owner", "tutor"]

        return True
