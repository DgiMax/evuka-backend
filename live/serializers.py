import pytz
from datetime import datetime
from rest_framework import serializers
from courses.models import Course
from .models import LiveClass, LiveLesson, LessonResource


class LessonResourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = LessonResource
        fields = ["id", "title", "file", "uploaded_at"]
        read_only_fields = ["uploaded_at"]


class LiveLessonSerializer(serializers.ModelSerializer):
    resources = LessonResourceSerializer(many=True, read_only=True)
    effective_end_datetime = serializers.DateTimeField(read_only=True)
    status = serializers.ReadOnlyField()

    class Meta:
        model = LiveLesson
        fields = [
            "id",
            "live_class",
            "title",
            "description",
            "start_datetime",
            "end_datetime",
            "effective_end_datetime",
            "extension_minutes",
            "is_mic_locked",
            "is_camera_locked",
            "chat_room_id",
            "resources",
            "status",
            "is_cancelled",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "chat_room_id",
            "created_at",
            "updated_at",
            "live_class",
            "is_mic_locked",
            "is_camera_locked",
            "extension_minutes",
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

    def validate_timezone(self, value):
        if value not in pytz.common_timezones:
            raise serializers.ValidationError("Invalid timezone identifier.")
        return value

    def validate(self, data):
        course = data.get('course')
        if course:
            if course.status != 'published':
                raise serializers.ValidationError({
                    "course": f"Cannot schedule live classes. Course status is '{course.get_status_display()}' (must be 'Published')."
                })

        recurrence = data.get('recurrence_type', self.instance.recurrence_type if self.instance else 'none')

        if recurrence == 'none':
            has_time = data.get('single_session_start') or (self.instance and self.instance.single_session_start)
            if not has_time:
                raise serializers.ValidationError({"single_session_start": "Required for one-time classes."})

        if recurrence == 'weekly':
            days = data.get('recurrence_days', {})
            if not days:
                raise serializers.ValidationError({"recurrence_days": "Required for weekly classes."})

            valid_days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            for day, time_str in days.items():
                if day not in valid_days:
                    raise serializers.ValidationError(f"Invalid day: {day}")
                try:
                    datetime.strptime(time_str, "%H:%M")
                except ValueError:
                    raise serializers.ValidationError(f"Invalid time format for {day}. Use HH:MM.")
        return data


class LiveClassMinimalSerializer(serializers.ModelSerializer):
    lessons_count = serializers.IntegerField(source='lessons.count', read_only=True)

    class Meta:
        model = LiveClass
        fields = (
            "id",
            "slug",
            "title",
            "timezone",
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