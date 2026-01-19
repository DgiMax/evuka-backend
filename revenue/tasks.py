from celery import shared_task
from django.db import transaction
from .models import Payout
from payments.services.paystack_payout import initiate_transfer
import logging

logger = logging.getLogger(__name__)


@shared_task
def process_payout_batch():
    """
    Scheduled task (e.g., every 10 mins) to process pending payouts.
    """
    # Fetch up to 20 pending payouts to avoid timeouts
    pending_payouts = Payout.objects.filter(status='pending').select_related('wallet')[:20]

    for payout_obj in pending_payouts:
        process_single_payout(payout_obj.id)


def process_single_payout(payout_id):
    try:
        with transaction.atomic():
            # Lock the row
            payout = Payout.objects.select_for_update().get(id=payout_id)

            if payout.status != 'pending':
                return

            # Resolve Recipient Code
            recipient_code = None
            wallet = payout.wallet

            if wallet.owner_user:
                if hasattr(wallet.owner_user, 'banking_details'):
                    recipient_code = wallet.owner_user.banking_details.paystack_recipient_code

            elif wallet.owner_org:
                # Logic for Org banking details (if you implemented OrgBankingDetails)
                # For now, we fail if it's an Org without linked details
                pass

            if not recipient_code:
                payout.status = 'failed'
                payout.failure_reason = "No linked banking details found."
                # Refund the wallet
                wallet.deposit(payout.amount, "Refund: Payout Failed (No Bank Details)", tx_type="refund")
                payout.save()
                return

            # Mark as processing
            payout.status = 'processing'
            payout.save()

        # Call Paystack API (Outside atomic block)
        response = initiate_transfer(
            amount=payout.amount,
            recipient_code=recipient_code,
            reference=str(payout.reference),
            reason=f"Evuka Payout {payout.reference}"
        )

        if not response.get('status'):
            # API Failure
            with transaction.atomic():
                payout = Payout.objects.select_for_update().get(id=payout.id)
                payout.status = 'failed'
                payout.failure_reason = response.get('message', 'Paystack Error')
                payout.save()

                # Refund the wallet
                payout.wallet.deposit(payout.amount, "Refund: Payout Gateway Error", tx_type="refund")

    except Exception as e:
        logger.error(f"Payout Error {payout_id}: {str(e)}")