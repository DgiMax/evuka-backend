import django_filters
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
from .models import Event

class EventFilter(django_filters.FilterSet):
    # Custom methods to match your existing logic
    category = django_filters.CharFilter(method='filter_by_category_hierarchy')
    type = django_filters.CharFilter(method='filter_event_types')
    price = django_filters.CharFilter(method='filter_by_price')
    upcoming = django_filters.CharFilter(method='filter_by_upcoming')

    class Meta:
        model = Event
        fields = ['category', 'type', 'price', 'upcoming']

    def filter_by_category_hierarchy(self, queryset, name, value):
        active_org = getattr(self.request, "active_organization", None)
        if active_org:
            return queryset.filter(course__org_category__name=value)
        return queryset.filter(course__global_subcategory__slug=value)

    def filter_event_types(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(event_type__in=value.split(","))

    def filter_by_price(self, queryset, name, value):
        if value == "free":
            return queryset.filter(is_paid=False)
        elif value == "paid":
            return queryset.filter(is_paid=True)
        return queryset

    def filter_by_upcoming(self, queryset, name, value):
        now = timezone.now()
        if value == "next_7_days":
            return queryset.filter(start_time__range=(now, now + timedelta(days=7)))
        elif value == "next_30_days":
            return queryset.filter(start_time__range=(now, now + timedelta(days=30)))
        elif value == "next_90_days":
            return queryset.filter(start_time__range=(now, now + timedelta(days=90)))
        return queryset