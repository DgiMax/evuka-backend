import uuid
from django.conf import settings
from django.db import models
from courses.models import Course
from events.models import Event
from organizations.models import Organization


class Order(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("paid", "Paid"),
        ("cancelled", "Cancelled"),
        ("refunded", "Refunded"),
    ]

    PAYMENT_STATUS_CHOICES = [
        ("unpaid", "Unpaid"),
        ("partially_paid", "Partially Paid"),
        ("paid", "Paid"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="orders"
    )
    order_number = models.CharField(
        max_length=50,
        unique=True,
        editable=False
    )
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default="unpaid")

    notes = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Order {self.order_number} - {self.user}"

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = str(uuid.uuid4()).split("-")[0].upper()
        super().save(*args, **kwargs)

    @property
    def amount_paid(self):
        """Sum only successful Paystack (or other) payments."""
        return sum(p.amount for p in self.payments.filter(status="successful"))

    def update_payment_status(self):
        """Update order and payment status based on total successful payments."""
        paid = self.amount_paid

        if paid == 0:
            self.payment_status = "unpaid"
            self.status = "pending"
        elif paid < self.total_amount:
            self.payment_status = "partially_paid"
            self.status = "pending"
        else:
            self.payment_status = "paid"
            self.status = "paid"

        self.save(update_fields=["payment_status", "status"])


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items"
    )
    course = models.ForeignKey(
        Course,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="order_items"
    )
    event = models.ForeignKey(
        Event,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="order_items"
    )
    organization = models.ForeignKey(
        Organization,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="order_items"
    )
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "Order Item"
        verbose_name_plural = "Order Items"

    def __str__(self):
        item_name = self.course.title if self.course \
            else self.event.title if self.event \
            else self.organization.name if self.organization \
            else "Unknown Item"
        return f"{item_name} × {self.quantity}"

    def clean(self):
        """Ensure that exactly one purchasable item type is linked."""
        linked_items = [self.course, self.event, self.organization]

        linked_count = sum(1 for item in linked_items if item is not None)

        if linked_count == 0:
            raise ValueError("OrderItem must be linked to a course, event, or organization.")
        if linked_count > 1:
            raise ValueError("OrderItem cannot be linked to more than one item type (course, event, or organization).")