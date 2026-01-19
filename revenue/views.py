import logging
import requests
from decimal import Decimal
from django.conf import settings
from django.core.cache import cache  # <--- Added for caching bank list
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db import transaction

from .models import Wallet, Payout
from users.models import BankingDetails
from .serializers import (
    WalletSerializer,
    BankingDetailsSerializer,
    PayoutSerializer
)

PAYSTACK_SECRET = settings.PAYSTACK_SECRET_KEY
logger = logging.getLogger(__name__)


class RevenueDashboardView(APIView):
    """
    Consolidated Dashboard Data:
    1. Wallet Balance & History
    2. Banking Details (if verified)
    3. Recent Payout Requests
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        # 1. Get or Create Personal Wallet
        wallet, _ = Wallet.objects.get_or_create(owner_user=user)

        # 2. Get Banking Details
        banking_data = None
        if hasattr(user, 'banking_details'):
            banking_data = BankingDetailsSerializer(user.banking_details).data

        # 3. Get Recent Payouts
        recent_payouts = Payout.objects.filter(wallet=wallet).order_by('-created_at')[:5]

        return Response({
            "wallet": WalletSerializer(wallet).data,
            "banking": banking_data,
            "payouts": PayoutSerializer(recent_payouts, many=True).data
        })


class BankListView(APIView):
    """
    Fetches supported banks for KES from Paystack.
    Caches the result for 24 hours to avoid hitting Paystack API constantly.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # 1. Check Cache
        cached_banks = cache.get("paystack_kenya_banks")
        if cached_banks:
            return Response(cached_banks)

        # 2. Fetch from Paystack
        headers = {"Authorization": f"Bearer {PAYSTACK_SECRET}"}
        try:
            # We filter by currency=KES to get Kenyan banks
            res = requests.get("https://api.paystack.co/bank?currency=KES", headers=headers)

            if not res.ok:
                logger.error(f"Paystack Bank Fetch Failed: {res.text}")
                return Response({"error": "Failed to fetch banks"}, status=502)

            data = res.json().get('data', [])

            # Format strictly for frontend dropdown
            # Paystack returns 'type' which is crucial (kepss vs mobile_money)
            banks = [
                {
                    "name": b['name'],
                    "code": b['code'],
                    "type": b.get('type', 'kepss')  # Default to kepss if missing
                }
                for b in data
            ]

            # Manually insert M-Pesa at the top for better UX
            banks.insert(0, {"name": "M-Pesa", "code": "MPESA", "type": "mobile_money"})

            # 3. Cache it for 24 hours (86400 seconds)
            cache.set("paystack_kenya_banks", banks, 60 * 60 * 24)

            return Response(banks)

        except Exception as e:
            logger.error(f"Bank List Exception: {str(e)}")
            return Response({"error": str(e)}, status=500)


class AddBankingDetailsView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        account_number = request.data.get("account_number")
        bank_code = request.data.get("bank_code")

        if not account_number or not bank_code:
            return Response({"error": "Account Number and Bank Code are required."}, status=400)

        # --- 1. CONFIGURATION FOR KENYA (KES) ---
        is_mpesa = bank_code == "MPESA"

        # Paystack Requirement:
        # Kenyan Banks -> type: 'kepss'
        # Mobile Money -> type: 'mobile_money', bank_code: 'MPESA'

        payload = {
            "type": "mobile_money" if is_mpesa else "kepss",
            "name": user.get_full_name() or user.username,
            "account_number": account_number,
            "bank_code": "MPESA" if is_mpesa else bank_code,
            "currency": "KES"
        }

        headers = {"Authorization": f"Bearer {PAYSTACK_SECRET}"}

        try:
            logger.debug(f"Paystack Request: {payload}")

            res = requests.post("https://api.paystack.co/transferrecipient", json=payload, headers=headers)
            res_data = res.json()

            if not res.ok or not res_data.get('status'):
                error_message = res_data.get('message', 'Verification failed')
                logger.error(f"Paystack Verification Error: {res_data}")
                return Response({"error": f"Paystack Error: {error_message}"}, status=400)

            data = res_data['data']

            # --- 2. SAVE SECURELY ---
            BankingDetails.objects.update_or_create(
                user=user,
                defaults={
                    "paystack_recipient_code": data['recipient_code'],
                    "bank_name": data['details'].get('bank_name', 'Mobile Money'),
                    "display_number": f"****{account_number[-4:]}",
                    "is_verified": True
                }
            )

            return Response({"message": "Banking details saved successfully!"})

        except Exception as e:
            logger.exception("Add Banking Details Error")
            return Response({"error": str(e)}, status=500)


class RequestPayoutView(APIView):
    """
    Allows a user to withdraw funds.
    Validates balance and banking details before locking funds.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        amount = Decimal(request.data.get('amount', '0'))

        # 1. Basic Validation
        if amount < 100:
            return Response({"error": "Minimum withdrawal is KES 100"}, status=400)

        # 2. Check Wallet Balance
        wallet = get_object_or_404(Wallet, owner_user=user)

        if wallet.balance < amount:
            return Response({"error": "Insufficient balance"}, status=400)

        # 3. Check Banking Details
        if not hasattr(user, 'banking_details') or not user.banking_details.paystack_recipient_code:
            return Response({"error": "Please add verified banking details first."}, status=400)

        # 4. Process Withdrawal (Atomic Transaction)
        try:
            # The .withdraw method handles the locking (select_for_update)
            # and creates the Transaction record.
            wallet.withdraw(amount, description="Payout Request")

            # Create the Payout Tracking Record
            payout = Payout.objects.create(
                wallet=wallet,
                amount=amount,
                status='pending'
            )

            return Response(PayoutSerializer(payout).data, status=201)

        except Exception as e:
            return Response({"error": str(e)}, status=400)