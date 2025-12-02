import django_filters
from django.db.models import Q
from .models import Course


class CourseFilter(django_filters.FilterSet):
    # Custom method to handle Parent OR Child category matching
    category = django_filters.CharFilter(method='filter_by_category_hierarchy')

    # Standard filters
    level = django_filters.CharFilter(field_name='global_level__name', lookup_expr='iexact')
    min_price = django_filters.NumberFilter(field_name='price', lookup_expr='gte')
    max_price = django_filters.NumberFilter(field_name='price', lookup_expr='lte')

    class Meta:
        model = Course
        fields = ['category', 'level', 'min_price', 'max_price']

    def filter_by_category_hierarchy(self, queryset, name, value):
        """
        Filters courses if the slug matches either the GlobalSubCategory 
        OR the GlobalCategory (Parent).
        """
        # Handle cases where multiple categories might be sent (e.g. ?category=a&category=b)
        values = self.request.GET.getlist('category') if self.request else [value]

        if not values:
            return queryset

        # Logic: 
        # 1. Is the slug a Subcategory? (e.g., 'web-development')
        # 2. Is the slug a Main Category? (e.g., 'technology')
        return queryset.filter(
            Q(global_subcategory__slug__in=values) |
            Q(global_subcategory__category__slug__in=values)
        ).distinct()