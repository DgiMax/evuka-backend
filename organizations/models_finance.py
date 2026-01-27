from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from .constants import MIN_TUTOR_SHARE_PERCENT


class TutorAgreement(models.Model):
    organization = models.ForeignKey('organizations.Organization', on_delete=models.CASCADE,
                                     related_name="tutor_agreements")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="org_agreements")

    commission_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=MIN_TUTOR_SHARE_PERCENT,
        validators=[MinValueValidator(MIN_TUTOR_SHARE_PERCENT), MaxValueValidator(100.00)]
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    signed_by_user = models.BooleanField(default=False)

    class Meta:
        unique_together = ('organization', 'user')

    def __str__(self):
        return f"{self.user.username} @ {self.organization.name}: {self.commission_percent}%"

    def save(self, *args, **kwargs):
        if self.commission_percent < MIN_TUTOR_SHARE_PERCENT:
            raise ValidationError(f"Commission cannot be less than {MIN_TUTOR_SHARE_PERCENT}%.")
        super().save(*args, **kwargs)


class PendingEarning(models.Model):
    organization = models.ForeignKey('organizations.Organization', on_delete=models.CASCADE,
                                     related_name="pending_earnings")
    tutor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="pending_earnings")
    source_order_item = models.ForeignKey('orders.OrderItem', on_delete=models.SET_NULL, null=True)

    amount = models.DecimalField(max_digits=12, decimal_places=2)

    is_cleared = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    cleared_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.tutor.username} earned {self.amount} (Pending)"