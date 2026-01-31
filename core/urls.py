from django.urls import path
from .views import QuickNavDataView

urlpatterns = [
    path('nav/links/', QuickNavDataView.as_view(), name='nav-links-data'),
]