from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class User(AbstractUser):
    is_verified = models.BooleanField(default=False)

    # Platform-wide role flags
    is_tutor = models.BooleanField(default=False)
    is_student = models.BooleanField(default=False)
    is_publisher = models.BooleanField(default=False)

    def __str__(self):
        return self.username


class Subject(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True, blank=True, help_text="A URL-friendly version of the name")

    class Meta:
        ordering = ['name']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class CreatorProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="creator_profile"
    )

    display_name = models.CharField(max_length=255)
    bio = models.TextField(
        blank=True,
        help_text="Detailed bio. Use this for the 'About Me' section."
    )
    is_verified = models.BooleanField(
        default=False,
        help_text="Set to True once the tutor is approved."
    )

    profile_image = models.ImageField(
        upload_to='tutor_profiles/',
        null=True,
        blank=True,
        help_text="A clear, professional headshot."
    )
    headline = models.CharField(
        max_length=250,
        blank=True,
        help_text="A short, catchy tagline. e.g., 'Senior Django Developer'"
    )
    intro_video = models.FileField(
        upload_to='creator_videos/',
        max_length=500,
        blank=True,
        null=True,
        help_text="Optional: Upload an intro video file (e.g., .mp4, .webm)."
    )
    education = models.CharField(
        max_length=500,
        blank=True,
        help_text="Text field for their top education. e.g., 'B.Sc. in Computer Science at University of Nairobi'"
    )

    subjects = models.ManyToManyField(
        Subject,
        blank=True,
        related_name="tutors",
        help_text="Subjects this tutor teaches."
    )

    def __str__(self):
        return f"Creator: {self.display_name} ({self.user.username})"


class PublisherProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="publisher_profile"
    )

    display_name = models.CharField(
        max_length=255,
        help_text="The name displayed to buyers (e.g. 'Penguin Books' or 'John Doe')"
    )

    bio = models.TextField(
        blank=True,
        help_text="Detailed about section for the publisher/author."
    )

    is_verified = models.BooleanField(
        default=False,
        help_text="Set to True once the publisher is KYC approved."
    )

    profile_image = models.ImageField(
        upload_to='publisher_logos/',
        null=True,
        blank=True,
        help_text="Company Logo or Author Headshot."
    )

    headline = models.CharField(
        max_length=250,
        blank=True,
        help_text="A short, catchy tagline. e.g., 'Publishing African Stories since 2010'"
    )

    intro_video = models.FileField(
        upload_to='publisher_videos/',
        max_length=500,
        blank=True,
        null=True,
        help_text="Optional: Brand intro video."
    )

    website = models.URLField(
        blank=True,
        null=True,
        help_text="External website link."
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Publisher: {self.display_name} ({self.user.username})"


class BankingDetails(models.Model):
    """
    Stores payment destination tokens securely.
    We DO NOT store raw bank account numbers here.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="banking_details"
    )

    # The Token from Paystack (e.g., "RCP_1a2b3c4d")
    paystack_recipient_code = models.CharField(max_length=50, unique=True)

    # Metadata for display only (e.g. "Equity Bank", "****9876")
    bank_name = models.CharField(max_length=100)
    display_number = models.CharField(max_length=50)

    is_verified = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.bank_name} ({self.display_number})"


class StudentProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="marketplace_learner",
    )
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)
    bio = models.TextField(blank=True)
    preferences = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"MarketplaceLearner: {self.user.username}"


class NewsletterSubscriber(models.Model):
    email = models.EmailField(unique=True, help_text="Subscriber's email address")
    is_active = models.BooleanField(default=True, help_text="False if they unsubscribed")
    created_at = models.DateTimeField(auto_now_add=True)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="newsletter_subscription"
    )

    def __str__(self):
        return self.email