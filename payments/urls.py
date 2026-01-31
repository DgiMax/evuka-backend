from django.urls import path
from .views.initiate import initiate_payment
from .views.verify import verify_payment_view
from .views.webhooks import paystack_webhook
from .views.general import payment_methods, request_refund, list_refunds

urlpatterns = [
    path("initiate/<int:order_id>/", initiate_payment, name="initiate-payment"),
    path("verify/<str:reference>/", verify_payment_view, name="verify-payment"),
    path("webhook/paystack/", paystack_webhook, name="paystack-webhook"),
    path("methods/", payment_methods, name="payment-methods"),
    path("refund/<int:payment_id>/", request_refund, name="request-refund"),
    path("refunds/", list_refunds, name="list-refunds"),
]