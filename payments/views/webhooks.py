import hmac, hashlib, json, logging
from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from payments.models import Payment
from payments.utils import handle_successful_payment

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def paystack_webhook(request):
    paystack_signature = request.headers.get('x-paystack-signature')
    if not paystack_signature: return HttpResponse(status=400)

    secret = settings.PAYSTACK_SECRET_KEY.encode('utf-8')
    payload = request.body
    expected_signature = hmac.new(secret, payload, hashlib.sha256).hexdigest()

    if paystack_signature != expected_signature: return HttpResponse(status=400)

    try:
        event = json.loads(payload)
        if event['event'] == 'charge.success':
            data = event['data']
            payment = Payment.objects.get(reference_code=data['reference'])

            if payment.status != 'successful':
                payment.status = 'successful'
                payment.transaction_id = str(data['id'])
                payment.save()
                handle_successful_payment(payment)

    except (Payment.DoesNotExist, json.JSONDecodeError):
        return HttpResponse(status=200)

    return HttpResponse(status=200)