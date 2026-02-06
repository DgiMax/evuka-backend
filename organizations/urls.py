from django.urls import path, include
from rest_framework_nested import routers

from .views import (
    OrganizationViewSet, OrgMembershipViewSet, GuardianLinkViewSet, OrgTeamViewSet,
    ActiveOrganizationView, OrganizationCreateView,
    PublicOrgLevelListView,
    check_organization_access, OrganizationTeamView, OrgCategoryViewSet, OrgLevelViewSet, ValidateOrgContextView,
    OrganizationManagementView
)
from . import views_finance

router = routers.SimpleRouter()
router.register(r"memberships", OrgMembershipViewSet, basename="membership")
router.register(r"guardians", GuardianLinkViewSet, basename="guardian")
router.register(r'team', OrgTeamViewSet, basename='org-team-management')
router.register(r'', OrganizationViewSet, basename="organizations")

org_router = routers.NestedSimpleRouter(router, r'', lookup='organization')
org_router.register(r'categories', OrgCategoryViewSet, basename='org-categories')
org_router.register(r'levels', OrgLevelViewSet, basename='org-levels')

urlpatterns = [
    path('create/', OrganizationCreateView.as_view(), name='org-create'),
    path('current/', ActiveOrganizationView.as_view(), name='org-current'),
    path('check-access/<slug:slug>/', check_organization_access, name="check_organization_access"),
    path('validate-context/<slug:slug>/', ValidateOrgContextView.as_view(), name='validate-org-context'),
    path('org-team/<slug:slug>/', OrganizationTeamView.as_view(), name='org-team-public'),
    path('<slug:slug>/manage/', OrganizationManagementView.as_view(), name='org-management'),
    path('<slug:slug>/public-levels/', PublicOrgLevelListView.as_view(), name='org-public-levels'),

    path('<slug:org_slug>/finance/dashboard/', views_finance.get_tutor_earnings_dashboard, name='tutor-earnings-dashboard'),

    path(r'', include(router.urls)),
    path(r'', include(org_router.urls)),
]