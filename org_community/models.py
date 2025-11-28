from django.db import models
from django.conf import settings
from organizations.models import Organization
from organizations.models import OrgMembership


class OrgJoinRequest(models.Model):
    """
    Tracks requests from users wanting to join an organization.
    """
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="org_join_requests")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="join_requests")
    message = models.TextField(blank=True, help_text="Optional message from the user.")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (('user', 'organization', 'status'),)
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} -> {self.organization.name} ({self.status})"


class OrgInvitation(models.Model):
    """
    Tracks invitations sent from an organization (by an admin) to a user.
    """
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("rejected", "Rejected"),
        ("revoked", "Revoked"),
    ]

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="invitations_sent")
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                   related_name="org_invitations_sent")
    invited_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                     related_name="org_invitations_received")

    role = models.CharField(max_length=20, choices=OrgMembership.ROLE_CHOICES)

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (('organization', 'invited_user', 'status'),)
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.organization.name} -> {self.invited_user.username} ({self.status})"