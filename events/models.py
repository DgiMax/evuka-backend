from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from courses.models import Course
from courses.models import Enrollment
from organizations.models import OrgMembership


class Event(models.Model):
    """Main event model (e.g., webinar, workshop, course event)."""

    EVENT_TYPE_CHOICES = [
        ("online", "Online"),
        ("physical", "Physical"),
        ("hybrid", "Hybrid"),
    ]

    WHO_CAN_JOIN_CHOICES = [
        ("course_students", "Only Course Students"),
        ("org_students", "Organization Students"),
        ("anyone", "Any"),
    ]

    EVENT_STATUS_CHOICES = [
        ("draft", "Draft"),
        ("pending_approval", "Pending Approval"),
        ("approved", "Approved"),
        ("scheduled", "Scheduled"),
        ("ongoing", "Ongoing"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
        ("postponed", "Postponed"),
    ]

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="events",
        help_text="Related course for this event",
    )

    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    overview = models.TextField(blank=True)
    description = models.TextField(blank=True)

    event_type = models.CharField(
        max_length=20, choices=EVENT_TYPE_CHOICES, default="online"
    )
    event_status = models.CharField(
        max_length=20,
        choices=EVENT_STATUS_CHOICES,
        default="draft",
        help_text="Lifecycle status of the event"
    )

    location = models.CharField(max_length=255, blank=True)
    meeting_link = models.URLField(blank=True)

    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    timezone = models.CharField(max_length=50, default="Africa/Nairobi")

    who_can_join = models.CharField(
        max_length=20,
        choices=WHO_CAN_JOIN_CHOICES,
        default="anyone",
        help_text="Who is allowed to register for this event"
    )

    banner_image = models.ImageField(
        upload_to="events/banners/", blank=True, null=True
    )

    is_paid = models.BooleanField(default=False)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=10, default="KES")
    max_attendees = models.PositiveIntegerField(null=True, blank=True)

    registration_open = models.BooleanField(default=True)
    registration_deadline = models.DateTimeField(null=True, blank=True)

    organizer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="organized_events",
        help_text="The instructor or course creator hosting this event",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_time"]
        verbose_name = "Event"
        verbose_name_plural = "Events"

    def __str__(self):
        return self.title

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.who_can_join == "org_students" and (not self.course or not self.course.organization):
            raise ValidationError({
                "who_can_join": "Organization Students can only be selected if the course belongs to an organization."
            })

    def save(self, *args, **kwargs):
        """Auto-generate slug and organizer from course creator."""
        if not self.slug:
            self.slug = slugify(self.title)
        if not self.organizer and self.course and hasattr(self.course, "creator"):
            self.organizer = self.course.creator

        self.full_clean()
        super().save(*args, **kwargs)

    def get_total_confirmed_attendees(self):
        """Counts all confirmed attendees from BOTH direct registrations and successful e-commerce orders."""
        registrations_count = self.registrations.filter(status='registered').count()
        orders_count = 0
        return registrations_count + orders_count

    def is_full(self):
        """Checks if the event has reached its maximum attendee capacity."""
        if self.max_attendees is None:
            return False
        return self.get_total_confirmed_attendees() >= self.max_attendees

    def can_user_register(self, user):
        """Check if a user can register for this event."""
        if not self.registration_open:
            return False
        if self.registration_deadline and timezone.now() > self.registration_deadline:
            return False
        if self.is_full():
            return False

        if self.registrations.filter(user=user, status='registered').exists():
            return False

        if self.who_can_join == "course_students":
            is_enrolled = Enrollment.objects.filter(
                user=user,
                course=self.course,
                status="active"
            ).exists()
            if not is_enrolled:
                return False

        elif self.who_can_join == "org_students":
            if not self.course.organization:
                return False

            is_org_member = OrgMembership.objects.filter(
                user=user,
                organization=self.course.organization,
                is_active=True
            ).exists()
            if not is_org_member:
                return False

        return True

    @property
    def computed_status(self):
        """Dynamically computes real-time status based on timing and approval."""
        from django.utils import timezone

        if self.event_status in ["draft", "pending_approval", "cancelled", "postponed"]:
            if self.event_status == "pending_approval":
                now = timezone.now()
                if self.start_time <= now:
                    return "cancelled"
            return self.event_status

        now = timezone.now()

        if self.event_status == "approved":
            if now < self.start_time:
                return "scheduled"
            elif self.start_time <= now <= self.end_time:
                return "ongoing"
            else:
                return "completed"

        return self.event_status


class EventLearningObjective(models.Model):
    """Learning objectives related to the event."""

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="learning_objectives"
    )
    text = models.CharField(max_length=255)

    def __str__(self):
        return self.text


class EventAgenda(models.Model):
    """Agenda items for the event (timeline)."""

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="agenda"
    )
    time = models.CharField(max_length=100)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"{self.event.title} - {self.title}"


class EventRule(models.Model):
    """Event rules and guidelines."""

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="rules"
    )
    title = models.CharField(max_length=255)
    text = models.TextField()

    def __str__(self):
        return f"{self.title} ({self.event.title})"


class EventRegistration(models.Model):
    STATUS_CHOICES = [
        ("registered", "Registered"),
        ("attended", "Attended"),
        ("cancelled", "Cancelled"),
    ]
    PAYMENT_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("paid", "Paid"),
        ("free", "Free"),
    ]

    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="registrations"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="event_registrations"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="registered")
    payment_status = models.CharField(
        max_length=20, choices=PAYMENT_STATUS_CHOICES, default="free"
    )
    payment_reference = models.CharField(max_length=255, blank=True)

    registered_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("event", "user")
        ordering = ["-registered_at"]

    def __str__(self):
        return f"{self.user} → {self.event} ({self.status})"


class EventAttachment(models.Model):
    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="attachments"
    )
    file = models.FileField(upload_to="event_attachments/")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Attachment for {self.event.title}"