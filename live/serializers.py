import pytz
from datetime import datetime, timedelta
from django.utils import timezone
import uuid
from django.db.models import Q
from rest_framework import serializers
from courses.models import Course, Enrollment
from .models import LiveClass, LiveLesson, LessonResource


class LiveClassMinimalSerializer(serializers.ModelSerializer):
    lessons_count = serializers.IntegerField(source='lessons.count', read_only=True)

    class Meta:
        model = LiveClass
        fields = [
            "id", "slug", "title", "recurrence_type",
            "start_date", "lessons_count", "recurrence_days"
        ]


class LessonResourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = LessonResource
        fields = ["id", "title", "file", "uploaded_at"]
        read_only_fields = ["uploaded_at"]


class LiveLessonSerializer(serializers.ModelSerializer):
    resources = LessonResourceSerializer(many=True, read_only=True)
    status = serializers.ReadOnlyField()
    effective_end_datetime = serializers.DateTimeField(read_only=True)

    live_class = serializers.PrimaryKeyRelatedField(
        queryset=LiveClass.objects.all(),
        required=False
    )

    class Meta:
        model = LiveLesson
        fields = [
            "id", "live_class", "title", "description", "start_datetime",
            "end_datetime", "effective_end_datetime", "status", "resources",
            "chat_room_id", "is_cancelled", "extension_minutes",
            "is_mic_locked", "is_camera_locked"
        ]
        extra_kwargs = {
            'chat_room_id': {'required': False, 'allow_null': True}
        }

    def create(self, validated_data):
        """
        Handles manual lesson creation, ensuring a chat room ID is generated.
        """
        if not validated_data.get('chat_room_id'):
            validated_data['chat_room_id'] = uuid.uuid4().hex

        return super().create(validated_data)


class LiveClassStudentSerializer(serializers.ModelSerializer):
    active_lesson = serializers.SerializerMethodField()
    upcoming_lessons = serializers.SerializerMethodField()
    past_lessons = serializers.SerializerMethodField()

    class Meta:
        model = LiveClass
        fields = ["id", "slug", "title", "description", "timezone", "active_lesson", "upcoming_lessons", "past_lessons"]

    def get_active_lesson(self, obj):
        now = timezone.now()
        active = obj.lessons.filter(
            start_datetime__lte=now + timedelta(minutes=20),
            end_datetime__gt=now,
            is_cancelled=False
        ).first()
        return LiveLessonSerializer(active).data if active else None

    def get_upcoming_lessons(self, obj):
        now = timezone.now()
        lessons = obj.lessons.filter(start_datetime__gt=now + timedelta(minutes=20), is_cancelled=False).order_by(
            'start_datetime')[:5]
        return LiveLessonSerializer(lessons, many=True).data

    def get_past_lessons(self, obj):
        now = timezone.now()
        lessons = obj.lessons.filter(end_datetime__lte=now).order_by('-start_datetime')[:10]
        return LiveLessonSerializer(lessons, many=True).data


class CourseLiveHubSerializer(serializers.ModelSerializer):
    live_classes = LiveClassMinimalSerializer(many=True, read_only=True)
    ongoing_lessons = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = ["id", "slug", "title", "thumbnail", "ongoing_lessons", "live_classes"]

    def get_ongoing_lessons(self, obj):
        now = timezone.now()
        buffer_time = now + timedelta(minutes=20)
        lessons = LiveLesson.objects.filter(
            live_class__course=obj,
            start_datetime__lte=buffer_time,
            end_datetime__gt=now,
            is_cancelled=False
        )
        return LiveLessonSerializer(lessons, many=True).data


class LiveClassManagementSerializer(serializers.ModelSerializer):
    lessons_count = serializers.IntegerField(source='lessons.count', read_only=True)
    # This line is the missing link - it attaches the actual lesson objects
    lessons = LiveLessonSerializer(many=True, read_only=True)

    class Meta:
        model = LiveClass
        fields = "__all__"
        read_only_fields = ["slug", "creator", "creator_profile", "organization", "created_at", "updated_at"]

    def validate_timezone(self, value):
        if value not in pytz.common_timezones:
            raise serializers.ValidationError("Invalid timezone.")
        return value

    def validate(self, data):
        recurrence = data.get('recurrence_type', self.instance.recurrence_type if self.instance else 'none')
        if recurrence == 'none':
            if not data.get('single_session_start') and not (self.instance and self.instance.single_session_start):
                raise serializers.ValidationError({"single_session_start": "Required for one-time classes."})
        if recurrence == 'weekly':
            days = data.get('recurrence_days', {})
            if not days:
                raise serializers.ValidationError({"recurrence_days": "Required for weekly classes."})
            valid_days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            for day in days.keys():
                if day not in valid_days:
                    raise serializers.ValidationError(f"Invalid day: {day}")
        return data