from rest_framework import serializers
from .models import Wallet, Transaction, Payout
from users.models import BankingDetails

class BankingDetailsSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankingDetails
        fields = ['id', 'bank_name', 'display_number', 'is_verified', 'updated_at']
        read_only_fields = ['is_verified', 'updated_at']

class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = [
            'id',
            'tx_type',
            'amount',
            'description',
            'reference',
            'balance_after',
            'created_at'
        ]
        read_only_fields = fields

class PayoutSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payout
        fields = [
            'id',
            'amount',
            'status',
            'reference',
            'failure_reason',
            'created_at',
            'processed_at'
        ]
        read_only_fields = fields

class WalletSerializer(serializers.ModelSerializer):
    recent_transactions = serializers.SerializerMethodField()

    class Meta:
        model = Wallet
        fields = ['id', 'balance', 'currency', 'recent_transactions']
        read_only_fields = ['balance', 'currency']

    def get_recent_transactions(self, obj):
        txs = obj.transactions.order_by('-created_at')[:5]
        return TransactionSerializer(txs, many=True).data

class PayoutRequestSerializer(serializers.Serializer):
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=50.00,
        error_messages={"min_value": "Minimum withdrawal is KES 50"}
    )
    wallet_type = serializers.ChoiceField(
        choices=[('personal', 'Personal'), ('org', 'Organization')],
        default='personal'
    )
    org_id = serializers.IntegerField(required=False)