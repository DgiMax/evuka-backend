from rest_framework import serializers

from courses.services import CourseProgressService
from users.models import User
from courses.models import Enrollment, Course


class StudentSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="user.get_full_name", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    profile_image = serializers.ImageField(source="user.profile_image", read_only=True)
    course_title = serializers.CharField(source="course.title", read_only=True)
    course_slug = serializers.CharField(source="course.slug", read_only=True)
    organization_name = serializers.CharField(source="course.organization.name", read_only=True)

    progress_percent = serializers.SerializerMethodField()

    class Meta:
        model = Enrollment
        fields = [
            "id",
            "user",
            "full_name",
            "email",
            "profile_image",
            "course_title",
            "course_slug",
            "organization_name",
            "status",
            "progress_percent",
            "date_joined",
        ]

    def get_progress_percent(self, obj):
        service = CourseProgressService(obj.user, obj.course)
        progress_data = service.calculate_progress()
        return progress_data.get("percent", 0)


class StudentActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["suspend", "activate", "remove"])
