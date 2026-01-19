import requests
from django.conf import settings

PAYSTACK_SECRET = settings.PAYSTACK_SECRET_KEY
BASE_URL = "https://api.paystack.co"


def initialize_transaction(email, amount, reference, callback_url, method="card"):
    """
    Initialize Paystack payment session with specific channels.
    """
    url = f"{BASE_URL}/transaction/initialize"
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET}",
        "Content-Type": "application/json"
    }

    # Map your internal methods to Paystack payment channels
    channel_map = {
        "card": ["card"],
        "mobile_money_mpesa": ["mobile_money_mpesa"],
        "bank_transfer": ["bank"],
    }

    # Default to all channels if method is not recognized
    selected_channels = channel_map.get(method, ["card", "mobile_money_mpesa", "bank"])

    data = {
        "email": email,
        "amount": int(amount * 100),  # Convert to kobo/cents
        "reference": str(reference),
        "callback_url": callback_url,
        "currency": "KES",
        "channels": selected_channels,
        "metadata": {
            "payment_method": method  # Useful for debugging later
        }
    }

    try:
        response = requests.post(url, json=data, headers=headers)
        return response.json()
    except requests.exceptions.RequestException:
        return {"status": False, "message": "Connection error to Paystack"}


def verify_transaction(reference):
    """Verify a Paystack transaction status manually"""
    url = f"{BASE_URL}/transaction/verify/{reference}"
    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET}"}

    try:
        response = requests.get(url, headers=headers)
        return response.json()
    except requests.exceptions.RequestException:
        return {"status": False, "message": "Connection error"}


def refund_payment(transaction_id, amount=None, reason=None):
    """
    Initiate a refund.
    """
    url = f"{BASE_URL}/refund"
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET}",
        "Content-Type": "application/json",
    }

    data = {"transaction": transaction_id}
    if amount:
        data["amount"] = int(amount * 100)
    if reason:
        data["customer_note"] = reason

    try:
        response = requests.post(url, json=data, headers=headers)
        return response.json()
    except requests.exceptions.RequestException:
        return {"status": False, "message": "Connection error"}