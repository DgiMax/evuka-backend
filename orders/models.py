import uuid
from django.conf import settings
from django.db import models

from books.models import Book
from courses.models import Course
from events.models import Event
from organizations.models import Organization
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings


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

    is_distributed = models.BooleanField(default=False)

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

    def send_confirmation_email(self):
        subject = f"Payment Confirmed - Order #{self.order_number}"

        context = {
            "user": self.user,
            "order": self,
            "dashboard_url": "https://e-vuka.com/dashboard",
            "items": self.items.all(),
        }

        html_message = render_to_string(
            "emails/order_confirmed.html",
            context
        )
        plain_message = strip_tags(html_message)

        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[self.user.email],
            html_message=html_message,
            fail_silently=False,
        )

    @property
    def amount_paid(self):
        """Sum only successful Paystack (or other) payments."""
        return sum(p.amount for p in self.payments.filter(status="successful"))

    def update_payment_status(self):
        was_paid = self.status == "paid"

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

        if not was_paid and self.status == "paid":
            self.send_confirmation_email()


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items"
    )

    book = models.ForeignKey(
        Book,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="order_items"
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
        if self.book:
            return f"Book: {self.book.title}"
        elif self.course:
            return f"Course: {self.course.title}"
        elif self.event:
            return f"Event: {self.event.title}"
        elif self.organization:
            return f"Membership: {self.organization.name}"
        else:
            return "Unknown Item"

    def clean(self):
        """Ensure that exactly one purchasable item type is linked."""
        linked_items = [self.course, self.event, self.organization, self.book]

        linked_count = sum(1 for item in linked_items if item is not None)

        if linked_count == 0:
            raise ValueError("OrderItem must be linked to a book, course, event, or organization.")
        if linked_count > 1:
            raise ValueError("OrderItem cannot be linked to more than one item type.")