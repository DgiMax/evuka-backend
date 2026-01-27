from decimal import Decimal
from django.db import transaction
from django.conf import settings
from django.contrib.auth import get_user_model

from revenue.models import Wallet, Transaction, Payout
from organizations.models import Organization
from organizations.models_finance import TutorAgreement, PendingEarning
from organizations.constants import MIN_TUTOR_SHARE_PERCENT
from payments.services.paystack_payout import create_transfer_recipient, initiate_transfer

PLATFORM_FEE_PERCENT = Decimal("0.10")

User = get_user_model()


def distribute_order_revenue(order):
    """
    Core settlement engine.
    Splits revenue between Platform, Organizations (Payroll model), and Independent Creators.
    """
    if getattr(order, 'is_distributed', False):
        return

    if Transaction.objects.filter(description__contains=f"Order #{order.order_number}").exists():
        return

    try:
        platform_wallet = Wallet.get_system_wallet()
    except Wallet.DoesNotExist:
        sys_org, _ = Organization.objects.get_or_create(
            name="Evuka Platform",
            slug="evuka-platform",
            defaults={'status': 'approved'}
        )
        platform_wallet, _ = Wallet.objects.get_or_create(owner_org=sys_org)

    with transaction.atomic():
        for item in order.items.all():

            gross_amount = Decimal(str(item.price))
            platform_fee = gross_amount * PLATFORM_FEE_PERCENT
            net_revenue = gross_amount - platform_fee

            platform_wallet.deposit(
                amount=platform_fee,
                description=f"Fee: {item} (Order #{order.order_number})",
                tx_type="fee",
                source_item=item
            )

            if item.course and item.course.organization:
                org = item.course.organization
                tutor = item.course.creator

                agreement = TutorAgreement.objects.filter(
                    organization=org,
                    user=tutor,
                    is_active=True
                ).first()

                tutor_percent = agreement.commission_percent if agreement else MIN_TUTOR_SHARE_PERCENT
                tutor_cut = net_revenue * (tutor_percent / 100)

                org_wallet, _ = Wallet.objects.get_or_create(owner_org=org)
                org_wallet.deposit(
                    amount=net_revenue,
                    description=f"Sale: {item.course.title} (Includes {tutor_percent}% Tutor Share)",
                    tx_type="credit",
                    source_item=item
                )

                PendingEarning.objects.create(
                    organization=org,
                    tutor=tutor,
                    source_order_item=item,
                    amount=tutor_cut
                )

            elif item.event and getattr(item.event, 'course', None) and item.event.course.organization:
                org = item.event.course.organization
                org_wallet, _ = Wallet.objects.get_or_create(owner_org=org)
                org_wallet.deposit(
                    amount=net_revenue,
                    description=f"Event: {item.event.title}",
                    tx_type="credit",
                    source_item=item
                )

            elif item.course:
                seller_wallet, _ = Wallet.objects.get_or_create(owner_user=item.course.creator)
                seller_wallet.deposit(
                    amount=net_revenue,
                    description=f"Sale: {item.course.title}",
                    tx_type="credit",
                    source_item=item
                )

            elif item.event:
                organizer = item.event.organizer or item.event.course.creator
                if organizer:
                    seller_wallet, _ = Wallet.objects.get_or_create(owner_user=organizer)
                    seller_wallet.deposit(
                        amount=net_revenue,
                        description=f"Event: {item.event.title}",
                        tx_type="credit",
                        source_item=item
                    )

            elif item.book:
                seller_wallet, _ = Wallet.objects.get_or_create(owner_user=item.book.created_by)
                seller_wallet.deposit(
                    amount=net_revenue,
                    description=f"Book: {item.book.title}",
                    tx_type="credit",
                    source_item=item
                )

            elif item.organization:
                seller_wallet, _ = Wallet.objects.get_or_create(owner_org=item.organization)
                seller_wallet.deposit(
                    amount=net_revenue,
                    description=f"Membership: {item.organization.name}",
                    tx_type="credit",
                    source_item=item
                )

        order.is_distributed = True
        order.save()


def process_payout_request(payout_id):
    """
    Takes a pending Payout request (Withdrawal) and executes it via Paystack Transfer API.
    """
    try:
        payout = Payout.objects.get(id=payout_id, status='pending')
    except Payout.DoesNotExist:
        return "Payout not found or already processed."

    wallet = payout.wallet

    account_name = "Unknown"
    account_number = "000000"
    bank_code = "MPESA"

    if wallet.owner_user:
        account_name = wallet.owner_user.username
    elif wallet.owner_org:
        account_name = wallet.owner_org.name

    recipient_resp = create_transfer_recipient(account_name, account_number, bank_code)

    if not recipient_resp.get('status'):
        payout.status = 'failed'
        payout.failure_reason = recipient_resp.get('message', 'Recipient creation failed')
        payout.save()
        wallet.deposit(payout.amount, "Refund: Failed Payout Recipient", tx_type="refund")
        return "Failed to create recipient."

    recipient_code = recipient_resp['data']['recipient_code']

    transfer_resp = initiate_transfer(
        amount=payout.amount,
        recipient_code=recipient_code,
        reference=str(payout.reference),
        reason=f"Payout for {account_name}"
    )

    if transfer_resp.get('status'):
        payout.status = 'processing'
        payout.save()
        return "Payout initiated successfully."
    else:
        payout.status = 'failed'
        payout.failure_reason = transfer_resp.get('message', 'Transfer initiation failed')
        payout.save()
        wallet.deposit(payout.amount, "Refund: Failed Payout Transfer", tx_type="refund")
        return "Payout failed at Paystack."