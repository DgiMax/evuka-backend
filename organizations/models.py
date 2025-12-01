from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.text import slugify
from datetime import timedelta


class Organization(models.Model):
    ORG_TYPES = [
        ("school", "School"),
        ("homeschool", "Homeschool Network"),
    ]

    MEMBERSHIP_PERIODS = [
        ("monthly", "Monthly"),
        ("yearly", "Yearly"),
        ("lifetime", "Lifetime"),
        ("free", "Free Access"),
    ]

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    org_type = models.CharField(max_length=20, choices=ORG_TYPES)
    description = models.TextField(blank=True, null=True)
    logo = models.ImageField(upload_to='org_logos/', null=True, blank=True)
    branding = models.JSONField(default=dict, blank=True)
    policies = models.JSONField(default=dict, blank=True)

    membership_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    membership_period = models.CharField(
        max_length=20, choices=MEMBERSHIP_PERIODS, default="free"
    )
    membership_duration_value = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Number of months/years if not lifetime"
    )

    approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1

            while Organization.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1

            self.slug = slug

        super().save(*args, **kwargs)


class OrgMembership(models.Model):
    ROLE_CHOICES = [
        ("owner", "Owner"),
        ("admin", "Admin"),
        ("tutor", "Tutor"),
        ("student", "Student"),
        ("parent", "Parent"),
        ("counselor", "Counselor"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memberships"
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="memberships"
    )

    level = models.ForeignKey(
        "organizations.OrgLevel",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="members"
    )
    subjects = models.ManyToManyField(
        "organizations.OrgCategory",
        blank=True,
        related_name="members"
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    date_joined = models.DateTimeField(default=timezone.now)

    expires_at = models.DateTimeField(null=True, blank=True)
    payment_status = models.CharField(
        max_length=20,
        choices=[("paid", "Paid"), ("pending", "Pending"), ("failed", "Failed"), ("free", "Free")],
        default="free"
    )

    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("user", "organization")

    def is_admin_or_owner(self):
        return self.role in ["admin", "owner"]

    def __str__(self):
        return f"{self.user} - {self.role} @ {self.organization}"

    def activate_membership(self):
        org = self.organization

        if org.membership_period == "lifetime":
            self.expires_at = None
        elif org.membership_period == "monthly":
            self.expires_at = timezone.now() + timedelta(days=30 * (org.membership_duration_value or 1))
        elif org.membership_period == "yearly":
            self.expires_at = timezone.now() + timedelta(days=365 * (org.membership_duration_value or 1))
        else:
            self.expires_at = None

        self.payment_status = "paid"
        self.is_active = True
        self.save()

    def sync_access(self):
        """
        Automatically enrolls the user in all applicable published organization courses
        and registers them for all upcoming, approved organization events based on their level.
        This is run when membership is first activated.
        """
        from courses.models import Course, Enrollment
        from events.models import EventRegistration, Event

        if not self.is_active or self.role != 'student':
            return

        course_qs = Course.objects.filter(
            organization=self.organization,
            status='published'
        )

        if self.level:
            course_qs = course_qs.filter(org_level=self.level)

        for course in course_qs:
            Enrollment.objects.get_or_create(
                user=self.user,
                course=course,
                defaults={
                    'role': 'student',
                    'status': 'active'
                }
            )

        now = timezone.now()
        event_qs = Event.objects.filter(
            course__organization=self.organization,
            event_status__in=['approved', 'scheduled'],
            start_time__gte=now
        )

        for event in event_qs:
            EventRegistration.objects.get_or_create(
                event=event,
                user=self.user,
                defaults={
                    'status': 'registered',
                    'payment_status': 'free'
                }
            )

    def save(self, *args, **kwargs):
        is_new_or_activated = (
                self.pk is None or
                (OrgMembership.objects.filter(pk=self.pk, is_active=False).exists() and self.is_active == True)
        )

        super().save(*args, **kwargs)

        if is_new_or_activated and self.role == 'student':
            self.sync_access()


class GuardianLink(models.Model):
    parent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="guardian_links_as_parent",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="guardian_links_as_student",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="guardian_links",
    )
    relationship = models.CharField(max_length=50)

    class Meta:
        unique_together = ("parent", "student", "organization")

    def __str__(self):
        return f"{self.parent} -> {self.student} @ {self.organization}"


class OrgCategory(models.Model):
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="categories"
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    thumbnail = models.ImageField(
        upload_to='org_category_thumbnails/',
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("organization", "name")
        ordering = ["organization", "name"]
        verbose_name_plural = "Organization Categories"

    def __str__(self):
        return f"{self.name} ({self.organization.name})"


class OrgLevel(models.Model):
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="levels"
    )
    name = models.CharField(max_length=100)
    order = models.PositiveIntegerField(
        default=0, help_text="Used for sorting levels"
    )
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("organization", "name")
        ordering = ["organization", "order"]
        verbose_name_plural = "Organization Levels"

    def __str__(self):
        return f"{self.name} ({self.organization.name})"