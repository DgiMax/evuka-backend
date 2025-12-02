import uuid
import calendar
from datetime import timedelta, date, datetime

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
            self.slug = slugify(f"{self.title}-{uuid.uuid4().hex[:8]}")
        if not self.meeting_link:
            domain = getattr(settings, "JITSI_DOMAIN", "meet.jit.si")
            room_name = uuid.uuid4().hex[:10]
            self.meeting_link = f"https://{domain}/{room_name}"
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

    def generate_lessons_batch(self, start_from=None, days_ahead=30):
        """
        Generates lessons for the next 'days_ahead' days.
        Does not generate duplicates if a lesson already exists on that date/time.
        """
        if self.recurrence_type != "weekly" or not self.recurrence_days:
            return

        batch_start = start_from or date.today()
        if batch_start < self.start_date:
            batch_start = self.start_date

        batch_end_limit = batch_start + timedelta(days=days_ahead)

        course_end = self.end_date or (self.start_date + timedelta(weeks=52))  # Default cap 1 year if no end date

        effective_end = min(batch_end_limit, course_end)

        if batch_start > effective_end:
            return

        days_map = {day: time for day, time in self.recurrence_days.items()}
        current_date = batch_start

        while current_date <= effective_end:
            weekday_name = calendar.day_name[current_date.weekday()]

            if weekday_name in days_map:
                time_str = days_map[weekday_name]
                try:
                    start_time = datetime.strptime(time_str, "%H:%M").time()

                    dt_start = datetime.combine(current_date, start_time)
                    dt_end = dt_start + timedelta(minutes=self.lesson_duration)
                    end_time = dt_end.time()

                    LiveLesson.objects.get_or_create(
                        live_class=self,
                        date=current_date,
                        start_time=start_time,
                        defaults={
                            'title': f"{self.title} - {weekday_name} Session",
                            'end_time': end_time,
                            'jitsi_room_name': None,
                            'jitsi_meeting_link': None
                        }
                    )
                except ValueError:
                    pass

            current_date += timedelta(days=1)


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
            domain = getattr(settings, "JITSI_DOMAIN", "meet.jit.si")
            self.jitsi_meeting_link = f"https://{domain}/{self.jitsi_room_name}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} ({self.live_class.title})"