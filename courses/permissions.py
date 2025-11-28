from rest_framework import permissions
from .models import Enrollment, Course, Lesson, Module


class IsEnrolled(permissions.BasePermission):
    """
    Custom permission to only allow users enrolled in a course.
    """
    message = "You must be enrolled in this course to perform this action."

    def has_permission(self, request, view):
        # Let IsAuthenticated handle the base check
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        """
        Check if the user is enrolled in the course associated with the object.
        This 'obj' can be a Course, Module, or Lesson.
        """

        course_to_check = None

        if isinstance(obj, Course):
            # The object is the course itself
            course_to_check = obj
        elif isinstance(obj, Module):
            # The object is a module, get its course
            course_to_check = obj.course
        elif isinstance(obj, Lesson):
            # The object is a lesson, get its module's course
            if obj.module:
                course_to_check = obj.module.course

        if not course_to_check:
            # If we couldn't determine a course, deny permission
            return False

        # Check if an active enrollment exists for this user and the determined course
        return Enrollment.objects.filter(
            user=request.user,
            course=course_to_check,
            status='active'
        ).exists()


class IsTutorOrOrgAdmin(permissions.BasePermission):
    """
    Allows access if:
    - User is creating an independent course AND user.is_tutor is True.
    OR
    - User is creating an org course AND is an owner/admin/tutor in that org.
    """
    message = 'You do not have permission to create this course.'

    def has_permission(self, request, view):
        if request.method == 'POST':  # Check only for create action
            active_org = getattr(request, 'active_organization', None)
            user = request.user

            if active_org:
                # Check if user has appropriate role in the active org
                return user.memberships.filter(
                    organization=active_org,
                    role__in=['owner', 'admin', 'tutor'],  # Define allowed roles
                    is_active=True
                ).exists()
            else:
                # Check if user is a platform tutor
                return getattr(user, 'is_tutor', False)

        # Allow other methods (GET, PUT, etc.) based on other permissions
        return True


