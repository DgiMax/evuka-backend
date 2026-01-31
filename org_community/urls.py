from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    OrganizationDiscoveryViewSet,
    RequestToJoinView,
    OrgJoinRequestViewSet,
    InvitationViewSet
)

router = DefaultRouter()
router.register(r'discover', OrganizationDiscoveryViewSet, basename='org-discover')
router.register(r'invitations', InvitationViewSet, basename='invitations')
router.register(r'requests', OrgJoinRequestViewSet, basename='requests')

urlpatterns = [
    path('request-join/', RequestToJoinView.as_view(), name='org-request-join'),
    path('', include(router.urls)),
]