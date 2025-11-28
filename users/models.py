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


class TutorPayoutMethod(models.Model):
    class MethodType(models.TextChoices):
        BANK_ACCOUNT = 'bank', 'Bank Account'
        MOBILE_MONEY = 'mobile', 'Mobile Money'

    profile = models.ForeignKey(
        CreatorProfile,
        on_delete=models.CASCADE,
        related_name="payout_methods"
    )
    method_type = models.CharField(
        max_length=20,
        choices=MethodType.choices,
        help_text="The type of payout method."
    )

    paystack_recipient_code = models.CharField(
        max_length=100,
        unique=True,
        help_text="Paystack's 'recipient_code' (e.g., RCP_...)"
    )

    display_details = models.CharField(
        max_length=100,
        help_text="Masked details for display, e.g., 'Access Bank (***123)'"
    )

    is_active = models.BooleanField(
        default=False,
        help_text="Is this the default method for payouts?"
    )

    class Meta:
        verbose_name = "Tutor Payout Method"
        verbose_name_plural = "Tutor Payout Methods"

    def __str__(self):
        return f"{self.profile.display_name} - {self.get_method_type_display()} ({self.display_details})"

    def save(self, *args, **kwargs):
        if self.is_active:
            TutorPayoutMethod.objects.filter(profile=self.profile, is_active=True).exclude(pk=self.pk).update(
                is_active=False)
        super().save(*args, **kwargs)


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