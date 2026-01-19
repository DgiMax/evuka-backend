from django.urls import path
from .views import (
    RevenueDashboardView,
    AddBankingDetailsView,
    RequestPayoutView,
    BankListView  # <--- Import this
)

urlpatterns = [
    path('dashboard/', RevenueDashboardView.as_view(), name='revenue-dashboard'),
    path('banking/add/', AddBankingDetailsView.as_view(), name='add-banking'),
    path('payout/request/', RequestPayoutView.as_view(), name='request-payout'),

    # New endpoint for dynamic bank list
    path('banks/', BankListView.as_view(), name='list-banks'),
]