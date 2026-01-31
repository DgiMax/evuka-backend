from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.conf import settings
from orders.models import Order
from payments.models import Payment
from payments.services.paystack import initialize_transaction

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def initiate_payment(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)

    if order.payment_status == 'paid':
        return Response({"message": "Order already paid"}, status=400)

    email_for_paystack = request.data.get('email', request.user.email)
    method = request.data.get('payment_method', 'card').lower()

    payment, created = Payment.objects.update_or_create(
        order=order,
        defaults={
            'amount': order.total_amount,
            'user': request.user,
            'payment_method': method,
            'provider': 'paystack',
            'status': 'pending'
        }
    )

    frontend_base_url = getattr(settings, 'FRONTEND_URL', 'http://127.0.0.1:3000')
    callback_url = f"{frontend_base_url}/order-confirmation/{payment.reference_code}"

    paystack_response = initialize_transaction(
        email=email_for_paystack,
        amount=payment.amount,
        reference=payment.reference_code,
        callback_url=callback_url,
        method=method
    )

    if paystack_response.get('status'):
        payment.metadata = {
            "authorization_url": paystack_response["data"]["authorization_url"],
            "access_code": paystack_response["data"]["access_code"],
        }
        payment.status = "processing"
        payment.save()

        return Response({
            'payment_url': paystack_response['data']['authorization_url'],
            'access_code': paystack_response['data']['access_code'],
            'reference': payment.reference_code
        })
    else:
        payment.status = "failed"
        payment.save()
        return Response({
            'error': paystack_response.get('message', 'Paystack initialization failed')
        }, status=400)