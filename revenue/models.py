from django.db import models
from django.conf import settings
from django.utils import timezone
from decimal import Decimal

User = settings.AUTH_USER_MODEL


class Wallet(models.Model):
    """
    Represents a wallet belonging to a user or an organization.
    """
    owner_user = models.OneToOneField(
        User, null=True, blank=True, on_delete=models.CASCADE, related_name="wallet"
    )
    owner_org = models.OneToOneField(
        "organizations.Organization", null=True, blank=True, on_delete=models.CASCADE, related_name="wallet"
    )
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=10, default="KES")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        if self.owner_user:
            return f"Wallet - {self.owner_user.username}"
        elif self.owner_org:
            return f"Wallet - {self.owner_org.name}"
        return "Wallet (unassigned)"

    def credit(self, amount: Decimal, description=""):
        """Add money to wallet."""
        self.balance = (self.balance or Decimal("0.00")) + Decimal(amount)
        self.save(update_fields=["balance"])
        Transaction.objects.create(
            wallet=self,
            tx_type="credit",
            amount=amount,
            description=description,
        )

    def debit(self, amount: Decimal, description=""):
        """Remove money from wallet."""
        if self.balance < amount:
            raise ValueError("Insufficient balance.")
        self.balance -= amount
        self.save(update_fields=["balance"])
        Transaction.objects.create(
            wallet=self,
            tx_type="debit",
            amount=amount,
            description=description,
        )


class Transaction(models.Model):
    """
    Records any wallet-related movement (credit/debit).
    """
    TX_TYPES = [
        ("credit", "Credit"),
        ("debit", "Debit"),
        ("commission", "Platform Commission"),
        ("org_share", "Organization Share"),
        ("tutor_income", "Tutor Income"),
    ]

    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="transactions")
    tx_type = models.CharField(max_length=30, choices=TX_TYPES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.tx_type} - {self.amount} ({self.wallet})"


class Payout(models.Model):
    """
    Tracks tutor or organization withdrawals.
    """
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="payouts")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reference = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(default=timezone.now)
    processed_at = models.DateTimeField(null=True, blank=True)

    def mark_completed(self):
        self.status = "completed"
        self.processed_at = timezone.now()
        self.save(update_fields=["status", "processed_at"])

    def __str__(self):
        return f"Payout {self.reference} - {self.amount} ({self.status})"