from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from payments.models import Payment
from payments.services.paystack import verify_transaction
from payments.utils import handle_successful_payment, get_redirect_context

@api_view(["GET"])
@permission_classes([AllowAny])
def verify_payment_view(request, reference):
    paystack_response = verify_transaction(reference)

    try:
        payment = Payment.objects.get(reference_code=reference)
    except Payment.DoesNotExist:
        return Response({"error": "Payment record not found"}, status=404)

    if paystack_response.get("status") and paystack_response["data"]["status"] == "success":
        if payment.status != "successful":
            payment.status = "successful"
            payment.transaction_id = str(paystack_response["data"]["id"])
            payment.save()
            handle_successful_payment(payment)

        return Response({
            "status": "success",
            "redirect_context": get_redirect_context(payment.order)
        })

    payment.status = "failed"
    payment.save()
    return Response({"error": "Payment verification failed"}, status=400)