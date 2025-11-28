from rest_framework import serializers
from django.utils import timezone
from courses.models import Course
from rest_framework.exceptions import PermissionDenied
from .models import Announcement, AnnouncementReadStatus
from organizations.models import OrgMembership
from django.contrib.contenttypes.models import ContentType
from notifications.models import Notification


class TargetCourseSerializer(serializers.ModelSerializer):
    """
    Read-only serializer to provide a simple list of
    course IDs and titles for dropdowns.
    """

    class Meta:
        model = Course
        fields = ["id", "title"]


class TutorAnnouncementSerializer(serializers.ModelSerializer):
    """
    Serializer for creating and managing announcements.
    Includes complex, context-aware validation.
    """
    creator_name = serializers.CharField(source="creator.get_full_name", read_only=True)
    organization_name = serializers.CharField(source="organization.name", read_only=True)

    class Meta:
        model = Announcement
        fields = [
            "id", "title", "content", "status", "publish_at",
            "audience_type", "courses", "organization", "organization_name",
            "creator", "creator_name", "published_at", "approver",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "organization", "creator", "published_at",
            "approver", "created_at", "updated_at",
            "creator_name", "organization_name",
        ]

    def validate(self, data):
        request = self.context['request']
        user = request.user
        active_org = getattr(request, "active_organization", None)

        audience_type = data.get('audience_type', getattr(self.instance, 'audience_type', None))
        courses = data.get('courses', getattr(self.instance, 'courses', []))
        status = data.get('status', getattr(self.instance, 'status', 'draft'))

        if self.instance and 'audience_type' in data and data['audience_type'] != self.instance.audience_type:
            raise serializers.ValidationError("Audience type cannot be changed after creation.")

        if self.instance and 'courses' in data and data['courses'] != self.instance.courses:
            raise serializers.ValidationError("Specific courses cannot be changed after creation.")

        if self.instance and self.instance.status == "published":
            if "title" in data or "content" in data or "audience_type" in data:
                raise serializers.ValidationError(
                    "Cannot edit core content of a published announcement. Please archive and create a new one.")

        if not self.instance:
            if active_org:
                try:
                    membership = OrgMembership.objects.get(user=user, organization=active_org)
                except OrgMembership.DoesNotExist:
                    raise serializers.ValidationError("You are not a member of this organization.")

                role = membership.role

                if role == 'tutor':
                    if audience_type not in ['my_org_courses', 'specific_courses']:
                        raise serializers.ValidationError(
                            f"As a Tutor, you can only select 'My Organization Courses' or 'Specific Courses'.")
                    if audience_type == 'specific_courses':
                        if not courses:
                            raise serializers.ValidationError(
                                "You must select at least one course for 'Specific Courses'.")
                        for course in courses:
                            if course.organization != active_org or course.creator != user:
                                raise serializers.ValidationError(f"You do not own the course: {course.title}")

                    if status in ['published', 'scheduled']:
                        data['status'] = 'pending_approval'

                elif role in ['admin', 'owner']:
                    if audience_type not in ['all_org_courses', 'my_org_courses', 'specific_courses']:
                        raise serializers.ValidationError(
                            f"As an Admin, you can only select 'All Organization Courses', 'My Organization Courses', or 'Specific Courses'.")
                    if audience_type == 'specific_courses':
                        if not courses:
                            raise serializers.ValidationError(
                                "You must select at least one course for 'Specific Courses'.")
                        for course in courses:
                            if course.organization != active_org:
                                raise serializers.ValidationError(
                                    f"The course '{course.title}' does not belong to this organization.")
                else:
                    raise serializers.ValidationError("You do not have permission to create announcements.")

            else:
                if not hasattr(user, 'creator_profile'):
                    raise serializers.ValidationError(
                        "You must have a Creator Profile to create personal announcements.")

                if audience_type not in ['all_personal_courses', 'specific_courses']:
                    raise serializers.ValidationError(
                        f"In your personal context, you can only select 'All Personal Courses' or 'Specific Courses'.")

                if audience_type == 'specific_courses':
                    if not courses:
                        raise serializers.ValidationError("You must select at least one course for 'Specific Courses'.")
                    for course in courses:
                        if course.organization is not None or course.creator != user:
                            raise serializers.ValidationError(
                                f"The course '{course.title}' is not one of your personal courses.")

                if status == 'pending_approval':
                    raise serializers.ValidationError("Personal announcements do not require approval.")

        return data


class StudentAnnouncementSerializer(serializers.ModelSerializer):
    creator_name = serializers.SerializerMethodField()
    organization_name = serializers.CharField(source='organization.name', read_only=True, allow_null=True)
    is_read = serializers.SerializerMethodField()

    class Meta:
        model = Announcement
        fields = [
            'id',
            'title',
            'content',
            'published_at',
            'creator_name',
            'organization_name',
            'is_read',
            'audience_type'
        ]

    def get_creator_name(self, obj):
        creator = obj.creator

        if hasattr(creator, 'creator_profile') and creator.creator_profile.display_name:
            return creator.creator_profile.display_name

        full_name = creator.get_full_name()
        if full_name.strip():
            return full_name

        return creator.username

    def get_is_read(self, obj):
        """
        Checks if a Notification exists for this user + this announcement
        and if that notification is marked as read.
        """
        user = self.context.get('request').user if self.context.get('request') else None

        if not user or not user.is_authenticated:
            return False

        ct = ContentType.objects.get_for_model(obj)

        return Notification.objects.filter(
            recipient=user,
            content_type=ct,
            object_id=obj.id,
            is_read=True
        ).exists()