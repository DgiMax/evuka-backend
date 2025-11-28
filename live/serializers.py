from rest_framework import serializers

from courses.models import Course
from .models import LiveClass, LiveLesson
from .utils.jitsi_token import generate_jitsi_token


class LiveLessonSerializer(serializers.ModelSerializer):
    jitsi_token = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = LiveLesson
        fields = [
            "id",
            "live_class",
            "title",
            "description",
            "date",
            "start_time",
            "end_time",
            "jitsi_room_name",
            "jitsi_meeting_link",
            "is_active",
            "created_at",
            "updated_at",
            "jitsi_token",
        ]
        read_only_fields = [
            "jitsi_room_name",
            "jitsi_meeting_link",
            "created_at",
            "updated_at",
            "live_class"
        ]

    def get_jitsi_token(self, obj):
        request = self.context.get("request")
        if not request or not hasattr(request, "user"):
            return None

        user = request.user
        if not user.is_authenticated:
            return None

        if obj.jitsi_meeting_link:
            return generate_jitsi_token(user, obj.jitsi_room_name)
        return None


class LiveClassSerializer(serializers.ModelSerializer):
    lessons = LiveLessonSerializer(many=True, read_only=True)

    class Meta:
        model = LiveClass
        fields = "__all__"
        read_only_fields = [
            "slug",
            "meeting_link",
            "created_at",
            "updated_at",
            "creator",
            "creator_profile",
        ]

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        lessons_data = representation.get('lessons')
        if lessons_data:
            lessons_serializer = LiveLessonSerializer(
                instance.lessons.all(),
                many=True,
                context=self.context
            )
            representation['lessons'] = lessons_serializer.data
        return representation


class LiveClassMinimalSerializer(serializers.ModelSerializer):
    lessons_count = serializers.IntegerField(source='lessons.count', read_only=True)

    class Meta:
        model = LiveClass
        fields = (
            "id",
            "slug",
            "title",
            "recurrence_type",
            "recurrence_days",
            "start_date",
            "lessons_count",
        )


class CourseWithLiveClassesSerializer(serializers.ModelSerializer):
    live_classes = LiveClassMinimalSerializer(many=True, read_only=True)

    class Meta:
        model = Course
        fields = (
            "id",
            "slug",
            "title",
            "thumbnail",
            "live_classes",
        )

