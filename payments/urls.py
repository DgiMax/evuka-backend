from django.urls import path
from . import views

urlpatterns = [
    path("initiate/<int:order_id>/", views.initiate_payment, name="initiate-payment"),
    path("verify/<str:reference>/", views.verify_payment_view, name="verify-payment"),
    path("methods/", views.payment_methods, name="payment-methods"),
    path("refund/<int:payment_id>/", views.request_refund, name="request-refund"),
    path("refunds/", views.list_refunds, name="list-refunds"),
]