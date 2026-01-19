from rest_framework import permissions
from .models import Organization, OrgMembership


def get_active_org(request):
    if hasattr(request, "active_organization") and request.active_organization:
        return request.active_organization

    slug = request.headers.get("X-Organization-Slug")
    if not slug:
        return None

    try:
        org = Organization.objects.get(slug=slug)
        request.active_organization = org
        return org
    except Organization.DoesNotExist:
        return None


class IsOrgMember(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        org = get_active_org(request)
        if not org:
            return False
        return OrgMembership.objects.filter(user=request.user, organization=org, is_active=True).exists()


class IsOrgAdminOrOwner(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        org = get_active_org(request)
        if not org:
            return False
        return OrgMembership.objects.filter(
            user=request.user, organization=org, role__in=['admin', 'owner'], is_active=True
        ).exists()

    def has_object_permission(self, request, view, obj):
        # This is critical for model viewsets operating on specific objects
        if not request.user.is_authenticated:
            return False

        # If the object itself is an organization, check membership directly
        if isinstance(obj, Organization):
            membership = OrgMembership.objects.filter(user=request.user, organization=obj, is_active=True).first()
            if not membership: return False

            if request.method == 'DELETE':
                return membership.role == 'owner'

            if request.method in ['PUT', 'PATCH']:
                new_status = request.data.get('status')
                if new_status in ['archived', 'suspended'] and membership.role != 'owner':
                    return False
                return membership.role in ['owner', 'admin']

            return True

        # If object belongs to an org (like a Course or Category), logic is handled in view get_queryset or similar
        return True


class IsOrgStaff(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        org = get_active_org(request)
        if not org:
            return False
        membership = OrgMembership.objects.filter(user=request.user, organization=org, is_active=True).first()
        if not membership:
            return False
        if membership.role == 'student':
            return False
        if membership.role == 'tutor':
            return request.method in permissions.SAFE_METHODS
        if membership.role in ['admin', 'owner']:
            return True
        return False