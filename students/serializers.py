from rest_framework import serializers
from users.models import User
from courses.models import Enrollment, Course


class StudentSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(source="course.title", read_only=True)
    course_slug = serializers.CharField(source="course.slug", read_only=True)
    organization_name = serializers.CharField(source="course.organization.name", read_only=True)
    instructor_name = serializers.CharField(source="course.creator.get_full_name", read_only=True)

    class Meta:
        model = Enrollment
        fields = [
            "id",
            "user",
            "course_title",
            "course_slug",
            "organization_name",
            "instructor_name",
            "status",
            "date_joined",
        ]
        depth = 1  # Expand user data slightly


class StudentActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["suspend", "activate", "remove"])
