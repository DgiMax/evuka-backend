from django.utils import timezone
from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status

from .models import Payment, update_order_payment_status, Refund
from orders.models import Order
from .services.paystack import initialize_transaction, verify_payment, refund_payment
from .utils import handle_successful_payment


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def initiate_payment(request, order_id):
    """
    Start a payment session.
    Handles both Free orders (instant access) and Paid orders (Paystack).
    """
    order = get_object_or_404(Order, id=order_id, user=request.user)

    # --- 1. HANDLE FREE ORDERS ---
    if order.total_amount <= 0:
        # Check if already processed to avoid duplicates
        if order.status == 'paid':
            return Response({"message": "Order already paid.", "redirect_url": "/dashboard"})

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

        # Triggers: Order Update + Access Grant (Books/Courses) + Revenue (0.00)
        success_message = handle_successful_payment(payment)

        return Response({
            "message": success_message,
            "free_order": True,
            "redirect_url": "/dashboard"
        })

    # --- 2. HANDLE PAID ORDERS (PAYSTACK) ---
    method = request.data.get("payment_method", "card").lower()
    email = request.data.get("email") or request.user.email

    if not email:
        return Response(
            {"error": "Email address is required for payment receipt."},
            status=400
        )

    # Create the pending payment record
    payment = Payment.objects.create(
        order=order,
        user=request.user,
        provider="paystack",
        payment_method=method,
        amount=order.total_amount,
        currency="KES",
    )

    # Construct the Callback URL (Where Paystack returns the user)
    # We use settings.SITE_URL if defined, otherwise default to localhost (update for production!)
    base_url = getattr(settings, 'SITE_URL', 'http://localhost:8000')
    callback_url = f"{base_url}/api/payments/verify/{payment.reference_code}/"

    # Call Paystack API
    response = initialize_transaction(
        email=email,
        amount=payment.amount,
        reference=payment.reference_code,
        callback_url=callback_url,  # <--- CRITICAL FIX: Was missing before
        method=method,
    )

    if response.get("status"):
        # Save Paystack metadata
        payment.metadata = {
            "authorization_url": response["data"]["authorization_url"],
            "access_code": response["data"]["access_code"],
        }
        payment.status = "processing"
        payment.save()

        return Response({
            "payment_url": response["data"]["authorization_url"],
            "access_code": response["data"]["access_code"],
            "reference": payment.reference_code,
            "method": method,
        })
    else:
        # Fail gracefully
        payment.status = "failed"
        payment.save()
        return Response(
            {"error": response.get("message", "Payment initialization failed")},
            status=400
        )


@api_view(["GET"])
@permission_classes([AllowAny])
def verify_payment_view(request, reference):
    """
    Called by the Frontend or Paystack Redirect to confirm payment.
    """
    # 1. Verify status with Paystack API
    paystack_response = verify_payment(reference)

    try:
        payment = Payment.objects.get(reference_code=reference)
    except Payment.DoesNotExist:
        return Response({"error": "Payment record not found"}, status=status.HTTP_404_NOT_FOUND)

    # 2. Check logic
    if paystack_response.get("status") and paystack_response["data"]["status"] == "success":

        # Idempotency: If already successful, just return success
        if payment.status == "successful":
            return Response({"message": "Payment already verified.", "status": "success"})

        # Mark as successful
        payment.status = "successful"
        payment.transaction_id = paystack_response["data"]["id"]
        # Save extra Paystack data for debugging if needed
        if not payment.metadata: payment.metadata = {}
        payment.metadata['paystack_response'] = paystack_response["data"]
        payment.save()

        # 3. TRIGGER FULFILLMENT (Access + Revenue)
        success_message = handle_successful_payment(payment)

        return Response({"message": success_message, "status": "success"})

    else:
        payment.status = "failed"
        payment.save()
        return Response(
            {"error": "Payment verification failed at provider level"},
            status=status.HTTP_400_BAD_REQUEST
        )


@api_view(["GET"])
@permission_classes([AllowAny])
def payment_methods(request):
    """List available payment methods for frontend"""
    methods = [
        {"key": "card", "name": "Credit/Debit Card"},
        {"key": "mobile_money_mpesa", "name": "M-Pesa"},
        {"key": "bank_transfer", "name": "Bank Transfer"},
    ]
    return Response(methods)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def request_refund(request, payment_id):
    """
    Initiate a refund for a successful payment.
    """
    payment = get_object_or_404(Payment, id=payment_id, user=request.user)

    if payment.status != "successful":
        return Response({"error": "Only successful payments can be refunded."}, status=400)

    # Default to full refund if amount not specified
    amount = float(request.data.get("amount", payment.amount))
    reason = request.data.get("reason", "Customer requested refund")

    if amount > float(payment.amount):
        return Response({"error": "Refund amount cannot exceed original payment."}, status=400)

    # Create Refund Record
    refund = Refund.objects.create(
        payment=payment,
        amount=amount,
        reason=reason,
        requested_by_user=True,
    )

    # Call Paystack Refund API
    response = refund_payment(payment.transaction_id, amount, reason)

    if response.get("status"):
        refund.status = "processed"
        refund.processed_at = timezone.now()
        refund.save()

        # Update Payment Status
        payment.status = "refunded"
        payment.save()

        # Update Order Status
        update_order_payment_status(payment.order)

        # TODO: You might want to revoke Course/Book access here (Future Enhancement)

        return Response({
            "message": "Refund processed successfully",
            "refund_id": refund.id,
            "reference": payment.reference_code,
        })
    else:
        refund.status = "failed"
        refund.save()
        return Response({
            "error": response.get("message", "Refund failed at provider"),
            "refund_id": refund.id,
        }, status=400)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_refunds(request):
    """List user's refund history"""
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