from django.db import models
from django.conf import settings
from django.utils import timezone

from organizations.models import Organization
from courses.models import Course
from django.contrib.auth import get_user_model

User = get_user_model()


class Announcement(models.Model):
    """
    An announcement created by a tutor, either personally or for an organization.
    """

    class AudienceType(models.TextChoices):
        ALL_PERSONAL_COURSES = "all_personal_courses", "All Personal Courses"
        SPECIFIC_COURSES = "specific_courses", "Specific Courses"
        MY_ORG_COURSES = "my_org_courses", "My Organization Courses"
        ALL_ORG_COURSES = "all_org_courses", "All Organization Courses"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING_APPROVAL = "pending_approval", "Pending Approval"
        SCHEDULED = "scheduled", "Scheduled"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    title = models.CharField(max_length=255)
    content = models.TextField(help_text="Markdown supported")

    creator = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="created_announcements"
    )
    organization = models.ForeignKey(
        Organization,
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name="announcements"
    )

    audience_type = models.CharField(
        max_length=50,
        choices=AudienceType.choices,
        help_text="Determines the audience scope"
    )
    courses = models.ManyToManyField(
        Course,
        blank=True,
        related_name="announcements",
        help_text="Select specific courses if audience type is 'Specific Courses'"
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT
    )
    publish_at = models.DateTimeField(
        null=True, blank=True,
        help_text="If status is 'Scheduled', set the future publication time"
    )
    published_at = models.DateTimeField(null=True, blank=True, editable=False)

    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_announcements",
        editable=False
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"


class AnnouncementReadStatus(models.Model):
    """
    Tracks which user has read which announcement. Powers the notification "unread" count.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="announcement_read_statuses"
    )
    announcement = models.ForeignKey(
        Announcement,
        on_delete=models.CASCADE,
        related_name="read_statuses"
    )
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("user", "announcement")
        ordering = ["-announcement__published_at"]

    def __str__(self):
        status = "Read" if self.is_read else "Unread"
        return f"{self.user.username} - {self.announcement.title} ({status})"

    def save(self, *args, **kwargs):
        if self.is_read and not self.read_at:
            self.read_at = timezone.now()
        super().save(*args, **kwargs)