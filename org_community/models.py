import uuid
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from organizations.models import Organization


class OrgJoinRequest(models.Model):
    ROLE_CHOICES = [
        ('tutor', 'Tutor'),
        ('admin', 'Admin'),
        ('member', 'Member'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="org_join_requests")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="join_requests")

    desired_role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='tutor')
    proposed_commission = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="The percentage commission the applicant wants (if applying as Tutor)."
    )

    message = models.TextField(blank=True, help_text="Optional message from the user.")

    status = models.CharField(
        max_length=20,
        choices=[("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected")],
        default="pending"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "organization", "status")
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} -> {self.organization.name} ({self.status})"


class AdvancedOrgInvitation(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('negotiating', 'Negotiating'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('revoked', 'Revoked'),
    ]

    GOV_ROLES = [
        ('owner', 'Owner'),
        ('admin', 'Admin'),
        ('tutor', 'Tutor'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="invitations")

    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="sent_invites"
    )
    email = models.EmailField()

    gov_role = models.CharField(max_length=20, choices=GOV_ROLES, default='tutor')
    gov_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    is_tutor_invite = models.BooleanField(default=False)
    tutor_commission = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    tutor_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Invite for {self.email} to {self.organization.name}"

    @property
    def is_fully_resolved(self):
        gov_done = self.gov_status in ['accepted', 'rejected', 'revoked']
        tutor_done = (not self.is_tutor_invite) or (self.tutor_status in ['accepted', 'rejected', 'revoked'])

        if self.gov_status == 'accepted' and self.is_tutor_invite:
            return self.tutor_status in ['accepted', 'rejected', 'revoked']

        return gov_done and tutor_done


class NegotiationLog(models.Model):
    invitation = models.ForeignKey(AdvancedOrgInvitation, on_delete=models.CASCADE, related_name="logs")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    action = models.CharField(max_length=50)
    previous_value = models.CharField(max_length=255)
    new_value = models.CharField(max_length=255)
    note = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)