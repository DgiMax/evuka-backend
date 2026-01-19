import uuid
import pytz
from datetime import timedelta
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from organizations.models import Organization
from users.models import CreatorProfile

TIMEZONE_CHOICES = [(tz, tz) for tz in pytz.common_timezones]


class LiveClass(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("scheduled", "Scheduled"),
        ("completed", "Completed"),
        ("archived", "Archived"),
    ]
    RECURRENCE_TYPE = [
        ("none", "One-Time"),
        ("weekly", "Weekly"),
    ]

    course = models.ForeignKey(
        "courses.Course",
        on_delete=models.CASCADE,
        related_name="live_classes"
    )
    organization = models.ForeignKey(
        Organization,
        null=True, blank=True,
        on_delete=models.SET_NULL
    )
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="live_classes"
    )
    creator_profile = models.ForeignKey(
        CreatorProfile,
        null=True, blank=True,
        on_delete=models.SET_NULL
    )

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    slug = models.SlugField(unique=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")

    timezone = models.CharField(max_length=64, choices=TIMEZONE_CHOICES, default="UTC")
    recurrence_type = models.CharField(max_length=20, choices=RECURRENCE_TYPE, default="none")
    recurrence_days = models.JSONField(default=dict, blank=True)

    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)

    single_session_start = models.TimeField(null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(default=60)

    requires_auth = models.BooleanField(default=True)
    allow_student_access = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"{self.title}-{uuid.uuid4().hex[:8]}")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} ({self.status})"


class LiveLesson(models.Model):
    live_class = models.ForeignKey(LiveClass, related_name="lessons", on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    start_datetime = models.DateTimeField(db_index=True)
    end_datetime = models.DateTimeField(db_index=True)

    chat_room_id = models.CharField(max_length=100, unique=True, default=uuid.uuid4)

    is_cancelled = models.BooleanField(default=False)
    extension_minutes = models.PositiveIntegerField(default=0)

    is_mic_locked = models.BooleanField(default=False)
    is_camera_locked = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["start_datetime"]
        unique_together = ['live_class', 'start_datetime']

    @property
    def effective_end_datetime(self):
        return self.end_datetime + timedelta(minutes=self.extension_minutes)

    @property
    def status(self):
        now = timezone.now()
        if self.is_cancelled:
            return "cancelled"
        if now < self.start_datetime:
            return "upcoming"
        if now > self.effective_end_datetime:
            return "completed"
        return "live"

    def __str__(self):
        return f"{self.title} - {self.start_datetime}"


class LessonResource(models.Model):
    lesson = models.ForeignKey(LiveLesson, related_name="resources", on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to="lesson_resources/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title