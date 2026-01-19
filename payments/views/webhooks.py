import hmac
import hashlib
import json
import logging
from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.db import transaction

from payments.models import Payment
from revenue.services.settlement import distribute_order_revenue
from courses.models import Enrollment  # Assuming you have these models
from events.models import EventRegistration

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def paystack_webhook(request):
    """
    Secure Webhook Listener.
    1. Verifies the message came from Paystack.
    2. Updates Payment status.
    3. Triggers Revenue Settlement.
    4. Grants User Access (Courses/Events).
    """

    # 1. Verify Signature (Security)
    paystack_signature = request.headers.get('x-paystack-signature')
    if not paystack_signature:
        return HttpResponse(status=400)

    secret = settings.PAYSTACK_SECRET_KEY.encode('utf-8')
    payload = request.body
    expected_signature = hmac.new(secret, payload, hashlib.sha256).hexdigest()

    if paystack_signature != expected_signature:
        return HttpResponse(status=400)

    # 2. Process Event
    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        return HttpResponse(status=400)

    if event['event'] == 'charge.success':
        data = event['data']
        reference = data['reference']

        try:
            payment = Payment.objects.select_related('order').get(reference_code=reference)

            # IDEMPOTENCY CHECK: Stop if already processed
            if payment.status == 'successful':
                return HttpResponse(status=200)

            with transaction.atomic():
                # Update Payment
                payment.status = 'successful'
                payment.transaction_id = str(data['id'])
                payment.save()

                # Update Order
                order = payment.order
                order.payment_status = 'paid'
                order.status = 'completed'
                order.save()

                # --- TRIGGER REVENUE ENGINE ---
                # This splits the money between Tutor/Publisher/Evuka
                distribute_order_revenue(order)

                # --- GRANT ACCESS ---
                # (You can move this to a services/access.py file if it grows)
                grant_product_access(order)

                logger.info(f"Payment {reference} processed successfully.")

        except Payment.DoesNotExist:
            logger.error(f"Webhook Error: Payment ref {reference} not found.")
            # Return 200 to stop Paystack from retrying a bad reference
            return HttpResponse(status=200)

    return HttpResponse(status=200)


def grant_product_access(order):
    """Helper to enroll students or give access to books"""
    for item in order.items.all():
        if item.course:
            Enrollment.objects.get_or_create(
                user=order.user,
                course=item.course,
                defaults={'status': 'active'}
            )
        elif item.event:
            EventRegistration.objects.get_or_create(
                user=order.user,
                event=item.event,
                defaults={'status': 'confirmed'}
            )