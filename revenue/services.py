import uuid
from decimal import Decimal
from django.db import transaction
from .models import Wallet, Transaction, Payout


PLATFORM_COMMISSION_RATE = Decimal("0.10")  # 10%
ORG_SHARE_RATE = Decimal("0.20")  # 20%


@transaction.atomic
def allocate_revenue(order):
    """
    Allocates revenue between tutor, org, and platform after a successful order.
    """
    total_amount = Decimal(order.amount)

    platform_cut = total_amount * PLATFORM_COMMISSION_RATE
    tutor_share = total_amount - platform_cut

    tutor_wallet = Wallet.objects.get(owner_user=order.tutor)

    # if tutor belongs to an organization
    if getattr(order.tutor, "organization", None):
        org_wallet = Wallet.objects.get(owner_org=order.tutor.organization)
        org_cut = tutor_share * ORG_SHARE_RATE
        tutor_share -= org_cut

        org_wallet.credit(org_cut, f"Org share from {order.course.title}")
        Transaction.objects.create(
            wallet=org_wallet,
            tx_type="org_share",
            amount=org_cut,
            description=f"Share from {order.course.title}",
        )

    # Tutor income
    tutor_wallet.credit(tutor_share, f"Income from {order.course.title}")
    Transaction.objects.create(
        wallet=tutor_wallet,
        tx_type="tutor_income",
        amount=tutor_share,
        description=f"Course: {order.course.title}",
    )

    # Platform commission (logged only)
    Transaction.objects.create(
        wallet=None,
        tx_type="commission",
        amount=platform_cut,
        description=f"Platform commission from {order.course.title}",
    )

    return {
        "tutor_share": tutor_share,
        "platform_cut": platform_cut,
    }


def initiate_payout(wallet: Wallet, amount: Decimal):
    """
    Starts a payout via Paystack (simulated — integrate Paystack here).
    """
    if wallet.balance < amount:
        raise ValueError("Insufficient balance.")

    reference = f"PAYOUT-{uuid.uuid4().hex[:10].upper()}"
    wallet.debit(amount, "Withdrawal request")

    payout = Payout.objects.create(
        wallet=wallet,
        amount=amount,
        reference=reference,
        status="processing",
    )

    # ✅ Integrate Paystack Transfer API here later
    # paystack.transfer_to_bank(amount, bank_account)
    # Once success → payout.mark_completed()

    return payout
