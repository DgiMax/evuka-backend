from rest_framework import serializers
from .models import Payment

class PaymentInitiationSerializer(serializers.Serializer):
    payment_method = serializers.ChoiceField(
        choices=[
            ("card", "Credit/Debit Card"),
            ("mobile_money_mpesa", "M-Pesa"),
            ("bank_transfer", "Bank Transfer"),
        ],
        required=True,
        error_messages={
            "invalid_choice": "Invalid payment method selected."
        }
    )

class RefundRequestSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    reason = serializers.CharField(required=False, allow_blank=True)