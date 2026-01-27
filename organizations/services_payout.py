from django.db import transaction
from django.utils import timezone
from revenue.models import Wallet, Transaction
from .models_finance import PendingEarning


def process_organization_payouts(organization):
    pending_list = PendingEarning.objects.filter(
        organization=organization,
        is_cleared=False
    )

    if not pending_list.exists():
        return "No pending payouts."

    try:
        org_wallet = Wallet.objects.get(owner_org=organization)
    except Wallet.DoesNotExist:
        return "Organization wallet not found."

    count = 0
    total_paid = 0

    with transaction.atomic():
        for earning in pending_list:
            if org_wallet.balance < earning.amount:
                continue

            org_wallet.withdraw(
                amount=earning.amount,
                description=f"Payout to {earning.tutor.username}",
                tx_type="debit"
            )

            tutor_wallet, _ = Wallet.objects.get_or_create(owner_user=earning.tutor)
            tutor_wallet.deposit(
                amount=earning.amount,
                description=f"Payout from {organization.name}",
                tx_type="credit"
            )

            earning.is_cleared = True
            earning.cleared_at = timezone.now()
            earning.save()

            count += 1
            total_paid += earning.amount

    return f"Successfully paid {count} tutors a total of {total_paid} KES."