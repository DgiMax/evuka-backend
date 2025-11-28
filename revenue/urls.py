from django.urls import path
from .views import RevenueOverviewView, InitiatePayoutView

urlpatterns = [
    path("overview/", RevenueOverviewView.as_view(), name="revenue-overview"),
    path("payout/", InitiatePayoutView.as_view(), name="initiate-payout"),
]