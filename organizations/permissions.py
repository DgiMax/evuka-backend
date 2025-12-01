from rest_framework import permissions

from .models import Organization


def get_active_org(request):
    """
    Helper to resolve organization context ONCE per request.
    It checks the request object first, then the header.
    """
    # 1. If we already found it, return it.
    if hasattr(request, "active_organization") and request.active_organization:
        return request.active_organization

    # 2. Look for header
    slug = request.headers.get("X-Organization-Slug")
    if not slug:
        return None

    # 3. Fetch and Cache
    try:
        org = Organization.objects.get(slug=slug)
        request.active_organization = org  # <--- Caching it here
        return org
    except Organization.DoesNotExist:
        return None


class IsOrgMember(permissions.BasePermission):
    """
    Allows access to ANY active member (Student, Tutor, Admin, Owner).
    """

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False

        org = get_active_org(request)  # <--- Uses the optimized helper
        if not org:
            return False

        # Optimized: Use exists() for speed
        return request.user.memberships.filter(organization=org, is_active=True).exists()


class IsOrgAdminOrOwner(permissions.BasePermission):
    """
    Strict access: Only Admins and Owners.
    """

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False

        org = get_active_org(request)
        if not org:
            return False

        return request.user.memberships.filter(
            organization=org,
            role__in=['admin', 'owner'],
            is_active=True
        ).exists()


class IsOrgStaff(permissions.BasePermission):
    """
    Dashboard Access Logic:
    1. Students -> DENIED (403).
    2. Tutors   -> READ ONLY (200 OK for lists, 403 for Actions like Create/Delete).
    3. Admins   -> FULL ACCESS.
    """

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False

        org = get_active_org(request)
        if not org:
            return False

        # Get specific membership
        membership = request.user.memberships.filter(organization=org, is_active=True).first()

        if not membership:
            return False

        # 1. Student -> DENY
        if membership.role == 'student':
            return False

            # 2. Tutor -> READ ONLY (Safe Methods)
        if membership.role == 'tutor':
            return request.method in permissions.SAFE_METHODS

        # 3. Admin/Owner -> ALLOW
        if membership.role in ['admin', 'owner']:
            return True

        return False