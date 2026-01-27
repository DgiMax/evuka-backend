from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    OrganizationDiscoveryViewSet,
    RequestToJoinView,
    OrgJoinRequestViewSet,
    InvitationViewSet,
    OrgSentInvitationsViewSet
)

router = DefaultRouter()
router.register(r'discover', OrganizationDiscoveryViewSet, basename='org-discover')
router.register(r'invitations', InvitationViewSet, basename='invitations')
router.register(r'manage/invitations', OrgSentInvitationsViewSet, basename='org-manage-invitations')
router.register(r'manage/requests', OrgJoinRequestViewSet, basename='org-manage-requests')

urlpatterns = [
    path('request-join/', RequestToJoinView.as_view(), name='org-request-join'),
    path('', include(router.urls)),
]