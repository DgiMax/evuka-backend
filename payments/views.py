from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from rest_framework import status

from events.models import EventRegistration
from organizations.models import OrgMembership
from .models import Payment, update_order_payment_status, Refund
from .services.paystack import initialize_payment, verify_payment, refund_payment
from orders.models import Order
from courses.models import Enrollment
from .utils import handle_successful_payment


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def initiate_payment(request, order_id):
    """Start a Paystack payment session"""
    order = get_object_or_404(Order, id=order_id, user=request.user)

    if order.total_amount <= 0:
        payment = Payment.objects.create(
            order=order,
            user=request.user,
            provider="internal",
            payment_method="free",
            amount=0,
            currency="KES",
            status="successful",
            transaction_id=f"FREE-{order.id}-{timezone.now().timestamp()}"
        )

        success_message = handle_successful_payment(payment)

        return Response({
            "message": success_message,
            "free_order": True,
            "redirect_url": "/dashboard/learning"
        })

    method = request.data.get("payment_method", "card").lower()

    email = request.data.get("email")

    if not email:
        email = request.user.email

    if not email:
        return Response(
            {"error": "Email address is required for payment receipt."},
            status=400
        )

    payment = Payment.objects.create(
        order=order,
        user=request.user,
        provider="paystack",
        payment_method=method,
        amount=order.total_amount,
        currency="KES",
    )

    response = initialize_payment(
        email=email,
        amount=payment.amount,
        reference=payment.reference_code,
        method=method,
    )

    if response.get("status"):
        payment.metadata = {
            "authorization_url": response["data"]["authorization_url"],
            "access_code": response["data"]["access_code"],
        }
        payment.status = "processing"
        payment.save()
        return Response({
            "payment_url": response["data"]["authorization_url"],
            "method": method,
        })
    else:
        payment.status = "failed"
        payment.save()
        return Response({"error": response.get("message", "Payment initialization failed")}, status=400)


@api_view(["GET"])
@permission_classes([AllowAny])
def verify_payment_view(request, reference):
    """
    Verifies a Paystack payment and creates enrollments/memberships.
    """
    response = verify_payment(reference)

    try:
        payment = Payment.objects.get(reference_code=reference)
    except Payment.DoesNotExist:
        return Response({"error": "Payment not found"}, status=status.HTTP_404_NOT_FOUND)

    if response.get("status") and response["data"]["status"] == "success":
        # 1. Update Payment Specifics (Paystack stuff)
        payment.status = "successful"
        payment.transaction_id = response["data"]["id"]
        payment.save()

        # 2. Call the Reusable Logic
        success_message = handle_successful_payment(payment)

        return Response({"message": success_message})
    else:
        payment.status = "failed"
        payment.save()
        return Response({"error": "Payment verification failed"}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
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
    Request a refund for a completed payment.
    """
    payment = get_object_or_404(Payment, id=payment_id, user=request.user)

    if not payment.is_successful:
        return Response({"error": "Only successful payments can be refunded."}, status=400)

    amount = float(request.data.get("amount", payment.amount))
    reason = request.data.get("reason", "")

    if amount > float(payment.amount):
        return Response({"error": "Refund amount cannot exceed the original payment."}, status=400)

    refund = Refund.objects.create(
        payment=payment,
        amount=amount,
        reason=reason,
        requested_by_user=True,
    )

    response = refund_payment(payment.transaction_id, amount, reason)

    if response.get("status"):
        refund.status = "processed"
        refund.processed_at = timezone.now()
        refund.save()

        payment.status = "refunded"
        payment.save()
        update_order_payment_status(payment.order)

        return Response({
            "message": "Refund processed successfully",
            "refund_id": refund.id,
            "reference": payment.reference_code,
        })
    else:
        refund.status = "failed"
        refund.save()
        return Response({
            "error": response.get("message", "Refund failed"),
            "refund_id": refund.id,
        }, status=400)


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
            "requested_on": r.created_at,
        }
        for r in refunds
    ]
    return Response(data)