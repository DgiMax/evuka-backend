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

    # 1. Get Payment Details from Frontend
    email = request.data.get('email', request.user.email)
    method = request.data.get('payment_method', 'card').lower() # 'card', 'mobile_money_mpesa', etc.

    # 2. Create/Update Payment Record
    # We use update_or_create to avoid duplicates if they click "Pay" twice
    payment, created = Payment.objects.update_or_create(
        order=order,
        status='pending',
        defaults={
            'amount': order.total_amount,
            'user': request.user,
            'email': email,
            # If you have a 'payment_method' field in your model, save it here:
            # 'payment_method': method
        }
    )

    # 3. Call Paystack API with the selected Method
    paystack_response = initialize_transaction(
        email=email,
        amount=payment.amount,
        reference=payment.reference_code,
        callback_url=settings.PAYSTACK_CALLBACK_URL,
        method=method # <--- PASSING THE CHANNEL HERE
    )

    if paystack_response.get('status'):
        return Response({
            'authorization_url': paystack_response['data']['authorization_url'],
            'access_code': paystack_response['data']['access_code'],
            'reference': payment.reference_code
        })
    else:
        return Response({
            'error': paystack_response.get('message', 'Paystack initialization failed')
        }, status=400)