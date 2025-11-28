from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    OrganizationViewSet, OrgMembershipViewSet, GuardianLinkViewSet, OrgTeamViewSet, OrgCategoryViewSet,
    OrgLevelViewSet, ActiveOrganizationView, OrganizationCreateView, OrgJoinRequestViewSet, OrgSentInvitationsViewSet,
    OrganizationRetrieveView, PublicOrgLevelListView, check_organization_access, OrganizationTeamView
)

router = DefaultRouter()


router.register(r"", OrganizationViewSet, basename="organizations")
router.register(r"memberships", OrgMembershipViewSet, basename="membership")
router.register(r"guardians", GuardianLinkViewSet, basename="guardian")
router.register(r'team', OrgTeamViewSet, basename='org-team-management')
router.register(r'categories', OrgCategoryViewSet, basename='org-categories')
router.register(r'levels', OrgLevelViewSet, basename='org-levels')
router.register(r'join-requests', OrgJoinRequestViewSet, basename='org-join-requests')
router.register(r'sent-invitations', OrgSentInvitationsViewSet, basename='org-sent-invitations')

urlpatterns = [
    path('create/', OrganizationCreateView.as_view(), name='org-create'),

    path('current/', ActiveOrganizationView.as_view(), name='org-current'),

    path('check-access/<slug:slug>/', check_organization_access, name="check_organization_access"),

    path('org-team/<slug:slug>/', OrganizationTeamView.as_view(), name='org-team-public'),

    path('<slug:slug>/details/', OrganizationRetrieveView.as_view(), name="org-details"),

    path('<slug:slug>/levels/', PublicOrgLevelListView.as_view(), name='org-public-levels'),

    path("", include(router.urls)),
]