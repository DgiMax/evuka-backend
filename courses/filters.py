from django_filters import rest_framework as filters
from django.db.models import Q
from .models import Course


class CourseFilter(filters.FilterSet):
    category = filters.CharFilter(method='filter_categories')
    level = filters.CharFilter(method='filter_levels')
    is_free = filters.BooleanFilter(field_name='price', lookup_expr='isnull')
    min_price = filters.CharFilter(method='filter_price_range')
    max_price = filters.CharFilter(method='filter_price_range')
    price_range = filters.CharFilter(method='filter_price_range')

    class Meta:
        model = Course
        fields = ['category', 'level', 'is_free', 'min_price', 'max_price', 'price_range']

    def filter_categories(self, queryset, name, value):
        slug_list = self.data.getlist('category')
        if not slug_list:
            return queryset

        q_objects = Q()
        for slug in slug_list:
            q_objects |= Q(global_subcategory__slug__iexact=slug)

        return queryset.filter(q_objects)

    def filter_levels(self, queryset, name, value):
        name_list = self.data.getlist('level')
        if not name_list:
            return queryset

        q_objects = Q()
        for level_name in name_list:
            q_objects |= Q(global_level__name__iexact=level_name)

        return queryset.filter(q_objects)

    def filter_price_range(self, queryset, name, value):
        min_val_str = self.data.get('min_price')
        max_val_str = self.data.get('max_price')

        if not min_val_str and not max_val_str:
            return queryset

        queryset = queryset.filter(price__isnull=False)

        if min_val_str:
            try:
                min_val = float(min_val_str)
                if min_val > 0:
                    queryset = queryset.filter(price__gte=min_val)
            except ValueError:
                return queryset.none()

        if max_val_str:
            try:
                max_val = float(max_val_str)
                queryset = queryset.filter(price__lte=max_val)
            except ValueError:
                return queryset.none()

        return queryset