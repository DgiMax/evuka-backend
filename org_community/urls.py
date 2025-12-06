from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    OrganizationDiscoveryViewSet,
    RequestToJoinView,
    OrgJoinRequestViewSet,
    UserInvitationsViewSet,
    UserJoinRequestViewSet, OrgSentInvitationsViewSet
)

router = DefaultRouter()
router.register(r'discover', OrganizationDiscoveryViewSet, basename='org-discover')
router.register(r'my-invitations', UserInvitationsViewSet, basename='my-invitations')
router.register(r'my-join-requests', UserJoinRequestViewSet, basename='my-join-requests')

router.register(r'manage/requests', OrgJoinRequestViewSet, basename='org-manage-requests')
router.register(r'manage/invitations', OrgSentInvitationsViewSet, basename='org-manage-invitations')

urlpatterns = [
    path('request-join/', RequestToJoinView.as_view(), name='org-request-join'),
    path('', include(router.urls)),
]