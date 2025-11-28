from rest_framework import serializers
from .models import Notification
from announcements.serializers import StudentAnnouncementSerializer


class NotificationSerializer(serializers.ModelSerializer):
    content_object = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            'id',
            'notification_type',
            'verb',
            'is_read',
            'created_at',
            'organization',
            'content_object'  # <--- Full Announcement Data
        ]

    def get_content_object(self, obj):
        # Safety check: if the source object was deleted, return None
        if not obj.content_object:
            return None

        if obj.notification_type == 'announcement':
            # Use the existing serializer so the frontend gets the exact same structure
            return StudentAnnouncementSerializer(obj.content_object, context=self.context).data

        # Future expansion:
        # if obj.notification_type == 'assignment':
        #     return AssignmentSerializer(obj.content_object).data

        return None