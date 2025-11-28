from rest_framework import permissions
from organizations.models import OrgMembership
from .models import LiveClass, LiveLesson


class IsTutorOrOrgAdmin(permissions.BasePermission):
    """
    Custom permission for Live Classes and Lessons.
    """

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated

        if not request.user.is_authenticated:
            return False

        if request.method == 'POST':
            active_org = getattr(request, 'active_organization', None)
            user = request.user

            if active_org:
                return user.memberships.filter(
                    organization=active_org,
                    role__in=['owner', 'admin', 'tutor'],
                    is_active=True
                ).exists()
            else:
                return hasattr(user, 'creator_profile') and user.creator_profile is not None

        return True

    def _get_object_owner(self, obj):
        if isinstance(obj, LiveClass):
            return obj.creator
        if isinstance(obj, LiveLesson):
            return obj.live_class.creator
        return None

    def has_object_permission(self, request, view, obj):
        user = request.user

        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated

        active_org = getattr(request, "active_organization", None)
        owner = self._get_object_owner(obj)

        if not owner or not user.is_authenticated:
            return False

        if user.is_superuser:
            return True

        if not active_org:
            return owner == user

        membership = OrgMembership.objects.filter(
            user=user, organization=active_org
        ).first()

        if not membership:
            return False

        if membership.role in ["admin", "owner"]:
            return True

        return owner == user