import uuid

from django.conf import settings
from django.db import models
from django.utils.text import slugify

from organizations.models import Organization
from users.models import CreatorProfile


def generate_slug(title):
    return slugify(f"{title}-{uuid.uuid4().hex[:8]}")


def get_jitsi_domain():
    """Builds the full Jitsi domain from settings."""
    domain = settings.JITSI_DOMAIN
    use_ssl = getattr(settings, "JITSI_USE_SSL", True)
    protocol = "https" if use_ssl else "http"
    return f"{protocol}://{domain}"


class LiveClass(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("scheduled", "Scheduled"),
        ("ongoing", "Ongoing"),
        ("completed", "Completed"),
    ]
    RECURRENCE_TYPE = [
        ("none", "One-Time"),
        ("weekly", "Weekly"),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    slug = models.SlugField(unique=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")

    organization = models.ForeignKey(
        Organization, null=True, blank=True, on_delete=models.SET_NULL
    )
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="live_classes"
    )
    creator_profile = models.ForeignKey(
        CreatorProfile, null=True, blank=True, on_delete=models.SET_NULL
    )
    course = models.ForeignKey(
        "courses.Course",
        on_delete=models.CASCADE,
        related_name="live_classes"
    )

    meeting_link = models.URLField(max_length=500, blank=True)
    recurrence_type = models.CharField(max_length=20, choices=RECURRENCE_TYPE, default="none")
    recurrence_days = models.JSONField(default=dict, blank=True,
                                       help_text="e.g. {'Monday': '10:00', 'Wednesday': '14:00'}")
    recurrence_update_mode = models.CharField(
        max_length=20,
        default="none",
        choices=[
            ("none", "Do not regenerate lessons"),
            ("future", "Regenerate future lessons only"),
            ("all", "Regenerate all lessons"),
        ],
    )

    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)

    lesson_duration = models.PositiveIntegerField(default=60, help_text="Duration in minutes")

    requires_auth = models.BooleanField(default=True)
    allow_student_access = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = generate_slug(self.title)
        if not self.meeting_link:
            domain = get_jitsi_domain()
            room_name = uuid.uuid4().hex[:10]
            self.meeting_link = f"{domain}/{room_name}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} ({self.course.title})"

    def get_jitsi_room_name(self):
        return self.slug.replace("-", "_")

    def can_join(self, user):
        if user == self.creator or user.is_staff:
            return True
        if self.allow_student_access:
            return True
        return False


class LiveLesson(models.Model):
    live_class = models.ForeignKey(
        LiveClass, related_name="lessons", on_delete=models.CASCADE
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    date = models.DateField(help_text="Start date of the lesson")
    start_time = models.TimeField()
    end_time = models.TimeField()

    jitsi_room_name = models.CharField(max_length=255, blank=True, null=True)
    jitsi_meeting_link = models.URLField(max_length=500, blank=True, null=True)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date", "start_time"]

    def save(self, *args, **kwargs):
        if not self.jitsi_room_name:
            slug = slugify(self.title)
            unique_id = uuid.uuid4().hex[:6]
            self.jitsi_room_name = f"{slug}-{unique_id}"
        if not self.jitsi_meeting_link:
            domain = get_jitsi_domain()
            self.jitsi_meeting_link = f"{domain}/{self.jitsi_room_name}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} ({self.live_class.title})"