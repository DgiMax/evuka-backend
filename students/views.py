from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q

from courses.models import Enrollment, Course
from organizations.models import OrgMembership
from .serializers import StudentSerializer, StudentActionSerializer
from .permissions import IsTutorOrOrgAdmin


class TutorStudentsViewSet(viewsets.GenericViewSet):
    """
    Handles fetching and managing students enrolled in a tutor's courses.
    Context-aware:
    - Personal: Students in tutor’s independent courses.
    - Organization: Students in organization courses.
        - Tutor: sees only his course students.
        - Admin/Owner: sees all org students.
    """

    permission_classes = [IsTutorOrOrgAdmin]
    serializer_class = StudentSerializer

    def get_queryset(self):
        user = self.request.user
        active_org = getattr(self.request, "active_organization", None)

        base_qs = Enrollment.objects.filter(role="student").select_related("course", "user", "course__organization")

        if active_org:
            # 🔹 If org context
            membership = OrgMembership.objects.filter(user=user, organization=active_org).first()

            if not membership:
                return Enrollment.objects.none()

            if membership.role in ["admin", "owner"]:
                return base_qs.filter(course__organization=active_org)
            else:
                return base_qs.filter(course__organization=active_org, course__creator=user)
        else:
            # 🔹 Personal context
            return base_qs.filter(course__organization__isnull=True, course__creator=user)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = StudentSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def manage(self, request, pk=None):
        """
        Perform actions like suspend, activate, remove on a student enrollment.
        """
        enrollment = self.get_queryset().filter(id=pk).first()
        if not enrollment:
            return Response(
                {"error": "Enrollment not found or unauthorized."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = StudentActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action = serializer.validated_data["action"]

        # 🧭 Handle actions
        if action == "suspend":
            enrollment.status = "Suspended"  # updated to match your new choice
            enrollment.save()
            message = "Student suspended successfully."
        elif action == "activate":
            enrollment.status = "active"
            enrollment.save()
            message = "Student reactivated successfully."
        elif action == "remove":
            enrollment.delete()
            message = "Student removed successfully."
        else:
            return Response(
                {"error": f"Invalid action '{action}'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response(
            {"message": message, "id": pk, "new_status": enrollment.status if action != "remove" else None},
            status=status.HTTP_200_OK,
        )
