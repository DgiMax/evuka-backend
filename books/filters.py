import django_filters
from django.db.models import Q
from .models import Book


class BookFilter(django_filters.FilterSet):
    # Use the same method pattern as your working CourseFilter
    category = django_filters.CharFilter(method='filter_by_category_nav')
    filter_category = django_filters.CharFilter(method='filter_by_category_checkboxes')

    # Format and Level
    book_format = django_filters.CharFilter(method='filter_by_format')
    reading_level = django_filters.CharFilter(method='filter_by_level')

    # Price
    min_price = django_filters.NumberFilter(field_name='price', lookup_expr='gte')
    max_price = django_filters.NumberFilter(field_name='price', lookup_expr='lte')

    class Meta:
        model = Book
        fields = ['category', 'filter_category', 'book_format', 'reading_level', 'min_price', 'max_price']

    def filter_by_category_nav(self, queryset, name, value):
        return queryset.filter(Q(categories__slug=value) | Q(subcategories__slug=value)).distinct()

    def filter_by_category_checkboxes(self, queryset, name, value):
        # This is how your Course setup handles multiple values
        values = self.request.GET.getlist('filter_category')
        if not values: return queryset
        return queryset.filter(categories__slug__in=values).distinct()

    def filter_by_format(self, queryset, name, value):
        values = self.request.GET.getlist('book_format')
        if not values: return queryset
        return queryset.filter(book_format__in=values)

    def filter_by_level(self, queryset, name, value):
        values = self.request.GET.getlist('reading_level')
        if not values: return queryset
        return queryset.filter(reading_level__in=values)