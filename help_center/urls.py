from django.urls import path, include

from help_center.views import HelpCenterView

urlpatterns = [
    path('', HelpCenterView.as_view(), name='help-center'),
]