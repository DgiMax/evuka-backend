from rest_framework import serializers
from .models import Payment, Refund

class PaymentInitiationSerializer(serializers.Serializer):
    """
    Validates the input when a user wants to PAY for an order.
    """
    email = serializers.EmailField(required=False)
    payment_method = serializers.ChoiceField(
        choices=[
            ("card", "Credit/Debit Card"),
            ("mobile_money_mpesa", "M-Pesa"),
            ("bank_transfer", "Bank Transfer"),
        ],
        required=False,
        default="card"
    )

class RefundRequestSerializer(serializers.Serializer):
    """
    Validates a request to return money to the customer.
    """
    amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        min_value=1
    )
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=500
    )

class PaymentSerializer(serializers.ModelSerializer):
    """
    Read-only view of an Incoming Payment.
    """
    class Meta:
        model = Payment
        fields = [
            'reference_code',
            'amount',
            'currency',
            'status',
            'payment_method',
            'transaction_id', # Paystack ID
            'created_at'
        ]
        read_only_fields = fields

class RefundSerializer(serializers.ModelSerializer):
    """
    Read-only view of a Refund.
    """
    payment_reference = serializers.CharField(source='payment.reference_code', read_only=True)

    class Meta:
        model = Refund
        fields = [
            'id',
            'payment_reference',
            'amount',
            'status',
            'reason',
            'created_at'
        ]
        read_only_fields = fields