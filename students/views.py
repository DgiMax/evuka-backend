from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q

from courses.models import Enrollment, Course
from organizations.models import OrgMembership
from .serializers import StudentSerializer, StudentActionSerializer
from .permissions import IsTutorOrOrgAdmin


class TutorStudentsViewSet(viewsets.GenericViewSet):
    permission_classes = [IsTutorOrOrgAdmin]
    serializer_class = StudentSerializer

    def get_queryset(self):
        user = self.request.user
        active_org = getattr(self.request, "active_organization", None)
        base_qs = Enrollment.objects.filter(role="student").select_related(
            "course", "user", "course__organization"
        ).order_by("-date_joined")

        if active_org:
            membership = OrgMembership.objects.filter(user=user, organization=active_org).first()
            if not membership:
                return Enrollment.objects.none()
            if membership.role in ["admin", "owner"]:
                return base_qs.filter(course__organization=active_org)
            return base_qs.filter(course__organization=active_org, course__creator=user)

        return base_qs.filter(course__organization__isnull=True, course__creator=user)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)

        stats = {
            "total": queryset.count(),
            "active": queryset.filter(status="active").count(),
            "suspended": queryset.filter(status="Suspended").count(),
            "completed": queryset.filter(status="completed").count(),
        }

        return Response({
            "students": serializer.data,
            "stats": stats
        })

    @action(detail=True, methods=["post"])
    def manage(self, request, pk=None):
        enrollment = self.get_queryset().filter(id=pk).first()
        if not enrollment:
            return Response({"error": "Unauthorized or not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = StudentActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        act = serializer.validated_data["action"]

        if act == "suspend":
            enrollment.status = "Suspended"
            enrollment.save()
            msg = "Student access suspended."
        elif act == "activate":
            enrollment.status = "active"
            enrollment.save()
            msg = "Student access restored."
        elif act == "remove":
            enrollment.delete()
            return Response({"message": "Student removed from course."}, status=status.HTTP_200_OK)

        return Response({
            "message": msg,
            "id": pk,
            "new_status": enrollment.status
        })
