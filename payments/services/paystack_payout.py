import requests
from django.conf import settings

PAYSTACK_SECRET = settings.PAYSTACK_SECRET_KEY
BASE_URL = "https://api.paystack.co"


def create_transfer_recipient(name, account_number, bank_code="MPESA"):
    """
    Creates a recipient on Paystack.
    bank_code: "MPESA" or valid bank code (e.g. "063")
    """
    url = f"{BASE_URL}/transferrecipient"
    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET}"}

    data = {
        "type": "mobile_money" if bank_code == "MPESA" else "nuban",
        "name": name,
        "account_number": account_number,
        "bank_code": bank_code,
        "currency": "KES"
    }

    resp = requests.post(url, json=data, headers=headers)
    return resp.json()


def initiate_transfer(amount, recipient_code, reference, reason="Payout"):
    """
    Initiates the actual money transfer.
    """
    url = f"{BASE_URL}/transfer"
    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET}"}

    data = {
        "source": "balance",
        "amount": int(float(amount) * 100),  # Paystack expects Kobo/Cents
        "recipient": recipient_code,
        "reason": reason,
        "reference": reference
    }

    resp = requests.post(url, json=data, headers=headers)
    return resp.json()