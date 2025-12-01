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
router.register(r'join-requests', OrgJoinRequestViewSet, basename='org-join-requests')
router.register(r'my-invitations', UserInvitationsViewSet, basename='my-invitations')
router.register(r'my-join-requests', UserJoinRequestViewSet, basename='my-join-requests')

urlpatterns = [
    path('request-join/', RequestToJoinView.as_view(), name='org-request-join'),
    path('sent-invitations/', OrgSentInvitationsViewSet.as_view({'get': 'list'}), name='org-invitations'),
    path('', include(router.urls)),
]