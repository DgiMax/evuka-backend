import django_filters
from .models import Organization

class OrganizationFilter(django_filters.FilterSet):
    """
    Filter set for public Organization discovery.
    """
    class Meta:
        model = Organization
        fields = {
            'org_type': ['exact'],
            'membership_period': ['exact'],
        }