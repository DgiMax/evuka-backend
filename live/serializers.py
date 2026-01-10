from rest_framework import serializers
from courses.models import Course
from .models import LiveClass, LiveLesson

class LiveLessonSerializer(serializers.ModelSerializer):
    """
    Standard serializer for listing lessons.
    Exposes playback details for students but HIDES the stream_key.
    """
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
            # New Fields
            "hls_playback_url",
            "chat_room_id",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "hls_playback_url",
            "chat_room_id",
            "created_at",
            "updated_at",
            "live_class"
        ]


class LiveClassSerializer(serializers.ModelSerializer):
    lessons = LiveLessonSerializer(many=True, read_only=True)

    class Meta:
        model = LiveClass
        fields = "__all__"
        read_only_fields = [
            "slug",
            "created_at",
            "updated_at",
            "creator",
            "creator_profile",
        ]

    def to_representation(self, instance):
        """
        Ensure nested lessons use the updated context (if needed).
        """
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


class LiveLessonCreateSerializer(serializers.ModelSerializer):
    """
    Specific serializer for manually adding a lesson.
    Allows writing to 'live_class'.
    """
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
            "is_active",
        ]


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