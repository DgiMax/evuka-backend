from django import forms
from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from .models import (
    BookCategory,
    BookSubCategory,
    Book,
    CourseBook,
    BookAccess
)

class BookAdminForm(forms.ModelForm):
    class Meta:
        model = Book
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'subcategories' in self.fields:
            self.fields['subcategories'].queryset = BookSubCategory.objects.select_related('category').order_by(
                'category__name', 'name'
            )

    def clean(self):
        cleaned_data = super().clean()
        categories = cleaned_data.get('categories')
        subcategories = cleaned_data.get('subcategories')

        if categories and subcategories:
            selected_category_ids = set(cat.id for cat in categories)
            invalid_subcategories = [
                f"{sub.name} ({sub.category.name})"
                for sub in subcategories
                if sub.category_id not in selected_category_ids
            ]

            if invalid_subcategories:
                raise forms.ValidationError(
                    f"The following subcategories do not belong to the selected categories: {', '.join(invalid_subcategories)}"
                )
        return cleaned_data

class BookSubCategoryInline(admin.TabularInline):
    model = BookSubCategory
    extra = 1
    prepopulated_fields = {'slug': ('name',)}

@admin.register(BookCategory)
class BookCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'subcategory_count')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}
    inlines = [BookSubCategoryInline]

    def subcategory_count(self, obj):
        return obj.subcategories.count()
    subcategory_count.short_description = 'Subcategories'

@admin.register(BookSubCategory)
class BookSubCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'slug')
    list_filter = ('category',)
    search_fields = ('name', 'category__name')
    autocomplete_fields = ('category',)
    prepopulated_fields = {'slug': ('name',)}

@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    form = BookAdminForm
    list_display = (
        'title',
        'status',
        'status_colored',
        'publisher_profile',
        'price_display',
        'book_format',
        'sales_count',
        'created_at'
    )
    list_filter = (
        'status',
        'is_free',
        'book_format',
        'reading_level',
        'created_at',
    )
    search_fields = (
        'title',
        'authors',
        'isbn',
        'publisher_profile__display_name',
        'created_by__email'
    )
    list_editable = ('status',)
    autocomplete_fields = ('publisher_profile', 'created_by')
    filter_horizontal = ('categories', 'subcategories')
    readonly_fields = ('id', 'view_count', 'sales_count', 'rating_avg', 'created_at', 'updated_at')
    save_on_top = True

    fieldsets = (
        ('General Info', {
            'fields': (('title', 'status'), 'subtitle', 'authors', 'isbn', 'publication_date', 'slug')
        }),
        ('Ownership', {
            'fields': ('created_by', 'publisher_profile'),
        }),
        ('Categorization', {
            'fields': ('categories', 'subcategories', 'tags', 'reading_level')
        }),
        ('Content & Files', {
            'fields': ('short_description', 'long_description', 'table_of_contents', 'cover_image', 'book_format', 'book_file', 'preview_file')
        }),
        ('Pricing & Commission', {
            'fields': (('currency', 'price', 'is_free'), 'referral_commission_percent', ('discount_price', 'discount_start_date', 'discount_end_date'))
        }),
        ('Stats', {
            'classes': ('collapse',),
            'fields': ('view_count', 'sales_count', 'rating_avg', 'created_at', 'updated_at', 'id'),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('publisher_profile')

    def status_colored(self, obj):
        colors = {
            'draft': '#777',
            'published': '#28a745',
            'archived': '#dc3545',
        }
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            colors.get(obj.status, '#000'),
            obj.get_status_display()
        )
    status_colored.short_description = 'Status Indicator'

    def price_display(self, obj):
        if obj.is_free:
            return "Free"
        return f"{obj.currency} {obj.price}"
    price_display.short_description = 'Price'

@admin.register(CourseBook)
class CourseBookAdmin(admin.ModelAdmin):
    list_display = ('book', 'course', 'integration_type', 'applied_commission_percent', 'created_at')
    list_filter = ('integration_type', 'created_at')
    search_fields = ('book__title', 'course__title')
    autocomplete_fields = ('book', 'course', 'added_by')
    readonly_fields = ('applied_commission_percent',)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('book', 'course')

@admin.register(BookAccess)
class BookAccessAdmin(admin.ModelAdmin):
    list_display = ('user', 'book', 'source', 'granted_at')
    list_filter = ('source', 'granted_at')
    search_fields = ('user__email', 'book__title', 'user__username')
    autocomplete_fields = ('user', 'book')
    readonly_fields = ('granted_at',)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'book')