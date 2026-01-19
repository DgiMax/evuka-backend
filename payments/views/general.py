from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils import timezone

from payments.models import Payment, Refund
from payments.services.paystack import refund_payment  # Use the function from services


@api_view(["GET"])
@permission_classes([AllowAny])
def payment_methods(request):
    """List available payment methods for frontend dropdown"""
    methods = [
        {"key": "card", "name": "Credit/Debit Card"},
        {"key": "mobile_money_mpesa", "name": "M-Pesa Mobile Money"},
        {"key": "bank_transfer", "name": "Bank Transfer"},
    ]
    return Response(methods)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def request_refund(request, payment_id):
    """
    Request a refund.
    NOTE: In a real platform, you should manually review refunds
    to ensure the Tutor hasn't already withdrawn the money.
    """
    payment = get_object_or_404(Payment, id=payment_id, user=request.user)

    if payment.status != "successful":
        return Response({"error": "Only successful payments can be refunded."}, status=400)

    amount = float(request.data.get("amount", payment.amount))
    reason = request.data.get("reason", "Customer Request")

    if amount > float(payment.amount):
        return Response({"error": "Refund amount cannot exceed original payment."}, status=400)

    # 1. Create Refund Record
    refund = Refund.objects.create(
        payment=payment,
        amount=amount,
        reason=reason,
        requested_by_user=True,
    )

    # 2. Call Paystack API
    response = refund_payment(payment.transaction_id, amount, reason)

    if response.get("status"):
        refund.status = "processed"
        refund.processed_at = timezone.now()
        refund.save()

        payment.status = "refunded"
        payment.save()

        # Optionally reverse the Wallet transaction here using Revenue App
        # (Advanced step for later)

        return Response({
            "message": "Refund processed successfully",
            "refund_id": refund.id
        })
    else:
        refund.status = "failed"
        refund.save()
        return Response({"error": response.get("message", "Refund failed")}, status=400)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_refunds(request):
    """List all refunds for the logged-in user"""
    refunds = Refund.objects.filter(payment__user=request.user).order_by("-created_at")
    data = [
        {
            "id": r.id,
            "payment_reference": r.payment.reference_code,
            "amount": r.amount,
            "reason": r.reason,
            "status": r.status,
            "date": r.created_at,
        }
        for r in refunds
    ]
    return Response(data)