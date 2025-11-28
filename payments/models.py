import uuid
from django.conf import settings
from django.db import models
from orders.models import Order


class Payment(models.Model):
    PROVIDER_CHOICES = [
        ("paystack", "Paystack"),
    ]

    METHOD_CHOICES = [
        ("card", "Credit/Debit Card"),
        ("mpesa", "M-Pesa Mobile Money"),
        ("bank_transfer", "Bank Transfer"),
    ]

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
    payment_method = models.CharField(max_length=20, choices=METHOD_CHOICES, default="card")

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default="KES")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

    transaction_id = models.CharField(max_length=255, null=True, blank=True, unique=True)
    reference_code = models.CharField(max_length=100, default=uuid.uuid4, unique=True)
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.payment_method.upper()} {self.amount} ({self.status})"

    @property
    def is_successful(self):
        return self.status == "successful"


class Refund(models.Model):
    STATUS_CHOICES = [
        ("requested", "Requested"),
        ("processed", "Processed"),
        ("failed", "Failed"),
    ]

    payment = models.ForeignKey(Payment, related_name="refunds", on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="requested")

    requested_by_user = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Refund {self.amount} ({self.status}) for {self.payment}"


def update_order_payment_status(order):
    total_paid = sum(p.amount for p in order.payments.filter(status="successful"))

    if total_paid >= order.total_amount:
        order.payment_status = "paid"
        order.status = "paid"
    elif total_paid > 0:
        order.payment_status = "partially_paid"
        order.status = "pending"
    else:
        order.payment_status = "unpaid"
        order.status = "pending"

    order.save()
    return order