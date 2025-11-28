# payments/services/paystack.py
import requests
from django.conf import settings

PAYSTACK_BASE_URL = "https://api.paystack.co"


def initialize_payment(email, amount, reference, method="card"):
    """Initialize Paystack payment session"""
    print("PAYMENT METHOD RECEIVED:", method)
    url = f"{PAYSTACK_BASE_URL}/transaction/initialize"
    headers = {
        "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json",
    }

    # Map your internal methods to Paystack payment channels
    channel_map = {
        "card": ["card"],
        "mobile_money_mpesa": ["mobile_money_mpesa"],
        "bank_transfer": ["bank"],
    }

    data = {
        "email": email,
        "amount": int(amount * 100),  # Paystack uses smallest currency unit
        "reference": str(reference),
        "callback_url": settings.PAYSTACK_CALLBACK_URL,
        "currency": "KES",
        "channels": channel_map.get(method, ["card"]),
    }
    print("CHANNELS USED:", channel_map.get(method, ["card"]))

    response = requests.post(url, json=data, headers=headers)
    return response.json()


def verify_payment(reference):
    """Verify a Paystack transaction"""
    url = f"{PAYSTACK_BASE_URL}/transaction/verify/{reference}"
    headers = {"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}
    response = requests.get(url, headers=headers)
    return response.json()


def refund_payment(transaction_id, amount=None, reason=None):
    """
    Initiate a refund on Paystack.
    amount is in normal units (KES), converted to the smallest currency unit.
    """
    url = f"{PAYSTACK_BASE_URL}/refund"
    headers = {
        "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json",
    }

    data = {
        "transaction": transaction_id,
    }
    if amount:
        data["amount"] = int(amount * 100)  # Paystack expects smallest unit
    if reason:
        data["customer_note"] = reason

    response = requests.post(url, json=data, headers=headers)
    return response.json()
