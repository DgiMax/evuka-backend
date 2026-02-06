from django.contrib import admin
from .models import HelpCategory, HelpArticle


@admin.register(HelpCategory)
class HelpCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'icon', 'order', 'slug')
    prepopulated_fields = {'slug': ('name',)}  # Automatically generates slug as you type name
    search_fields = ('name',)
    list_editable = ('order', 'icon')  # Quick edit from the list view


@admin.register(HelpArticle)
class HelpArticleAdmin(admin.ModelAdmin):
    list_display = ('question', 'category', 'is_published', 'is_featured', 'views_count', 'created_at')
    list_filter = ('category', 'is_published', 'is_featured')
    search_fields = ('question', 'answer')
    prepopulated_fields = {'slug': ('question',)}
    list_editable = ('is_published', 'is_featured')

    # Organize fields into sections
    fieldsets = (
        ('Content', {
            'fields': ('category', 'question', 'slug', 'answer')
        }),
        ('Visibility', {
            'fields': ('is_published', 'is_featured')
        }),
        ('Analytics (Read Only)', {
            'description': 'Performance metrics for this article',
            'fields': ('views_count', 'helpful_count', 'not_helpful_count'),
        }),
    )

    readonly_fields = ('views_count', 'helpful_count', 'not_helpful_count')