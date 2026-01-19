import uuid
from django.db import models
from django.conf import settings
from orders.models import Order


class Payment(models.Model):
    PROVIDER_CHOICES = [("paystack", "Paystack"), ("internal", "Internal")]
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("successful", "Successful"),
        ("failed", "Failed"),
        ("refunded", "Refunded"),
    ]

    order = models.ForeignKey(Order, related_name="payments", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, default="paystack")
    payment_method = models.CharField(max_length=50, default="card")  # stored as 'card', 'mpesa', etc.

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=10, default="KES")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

    # Paystack identifiers
    transaction_id = models.CharField(max_length=255, null=True, blank=True)
    reference_code = models.CharField(max_length=100, unique=True, default=uuid.uuid4)

    # Metadata to store authorization_url or debug info
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.reference_code} - {self.status}"


class Refund(models.Model):
    STATUS_CHOICES = [("requested", "Requested"), ("processed", "Processed"), ("failed", "Failed")]

    payment = models.ForeignKey(Payment, related_name="refunds", on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="requested")

    requested_by_user = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)