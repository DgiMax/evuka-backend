from django.urls import path
from .views.initiate import initiate_payment
from .views.webhooks import paystack_webhook
from .views.general import payment_methods, request_refund, list_refunds

urlpatterns = [
    # 1. Start Payment (Frontend calls this)
    path("initiate/<int:order_id>/", initiate_payment, name="initiate-payment"),

    # 2. The Webhook (Paystack calls this silently - NEW)
    path("webhook/paystack/", paystack_webhook, name="paystack-webhook"),

    # 3. General Utilities (Frontend dropdowns & history)
    path("methods/", payment_methods, name="payment-methods"),
    path("refund/<int:payment_id>/", request_refund, name="request-refund"),
    path("refunds/", list_refunds, name="list-refunds"),
]