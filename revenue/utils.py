from decimal import Decimal

def format_currency(amount: Decimal, currency="KES"):
    return f"{currency} {amount:,.2f}"
