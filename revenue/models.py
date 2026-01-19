import uuid
from decimal import Decimal
from django.db import models, transaction
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone


class Wallet(models.Model):
    owner_user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="wallet"
    )
    owner_org = models.OneToOneField(
        'organizations.Organization',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="wallet"
    )

    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="KES")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        owner = self.owner_user.username if self.owner_user else self.owner_org.name
        return f"{owner}'s Wallet ({self.currency} {self.balance})"

    @classmethod
    def get_system_wallet(cls):
        return cls.objects.get(owner_org__name="Evuka Platform")

    def deposit(self, amount, description, tx_type="credit"):
        with transaction.atomic():
            locked_wallet = Wallet.objects.select_for_update().get(pk=self.pk)
            locked_wallet.balance += Decimal(str(amount))
            locked_wallet.save()

            Transaction.objects.create(
                wallet=locked_wallet,
                tx_type=tx_type,
                amount=amount,
                description=description,
                balance_after=locked_wallet.balance
            )

    def withdraw(self, amount, description, tx_type="debit"):
        with transaction.atomic():
            locked_wallet = Wallet.objects.select_for_update().get(pk=self.pk)

            if locked_wallet.balance < Decimal(str(amount)):
                raise ValidationError(f"Insufficient funds. Available: {locked_wallet.balance}")

            locked_wallet.balance -= Decimal(str(amount))
            locked_wallet.save()

            Transaction.objects.create(
                wallet=locked_wallet,
                tx_type=tx_type,
                amount=-Decimal(str(amount)),
                description=description,
                balance_after=locked_wallet.balance
            )


class Transaction(models.Model):
    TX_TYPES = [
        ('credit', 'Credit'),
        ('debit', 'Debit'),
        ('fee', 'Platform Fee'),
        ('refund', 'Refund'),
    ]

    wallet = models.ForeignKey(Wallet, related_name="transactions", on_delete=models.CASCADE)
    tx_type = models.CharField(max_length=10, choices=TX_TYPES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=255)
    balance_after = models.DecimalField(max_digits=12, decimal_places=2)
    reference = models.CharField(max_length=100, default=uuid.uuid4)
    created_at = models.DateTimeField(auto_now_add=True)


class Payout(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    wallet = models.ForeignKey(Wallet, related_name="payouts", on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reference = models.CharField(max_length=100, unique=True, default=uuid.uuid4)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    failure_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)