from django.contrib import admin
from django.utils.html import format_html
from .models import HelpCategory, HelpArticle

@admin.register(HelpCategory)
class HelpCategoryAdmin(admin.ModelAdmin):
    list_display = ('order', 'icon_preview', 'name', 'slug', 'article_count')
    list_display_links = ('name',)
    list_editable = ('order', 'slug')
    search_fields = ('name', 'description')
    prepopulated_fields = {'slug': ('name',)}
    ordering = ('order',)

    def icon_preview(self, obj):
        icons = {
            'book': '📚',
            'credit-card': '💳',
            'video': '🎥',
            'shield': '🛡️',
            'settings': '⚙️',
        }
        return icons.get(obj.icon, '📄')
    icon_preview.short_description = 'Icon'

    def article_count(self, obj):
        return obj.articles.count()
    article_count.short_description = 'Articles'

@admin.register(HelpArticle)
class HelpArticleAdmin(admin.ModelAdmin):
    list_display = (
        'question',
        'category',
        'is_published',
        'is_featured',
        'views_count',
        'engagement_score'
    )
    list_filter = ('category', 'is_published', 'is_featured', 'created_at')
    search_fields = ('question', 'answer', 'category__name')
    prepopulated_fields = {'slug': ('question',)}
    list_editable = ('is_published', 'is_featured')
    readonly_fields = ('views_count', 'helpful_count', 'not_helpful_count', 'created_at', 'updated_at')
    save_on_top = True

    fieldsets = (
        ('Article Content', {
            'fields': ('category', 'question', 'slug', 'answer')
        }),
        ('Visibility & Promotion', {
            'fields': (('is_published', 'is_featured'),)
        }),
        ('Analytics & Engagement', {
            'classes': ('collapse',),
            'description': 'User feedback and view metrics.',
            'fields': (('views_count', 'helpful_count', 'not_helpful_count'), ('created_at', 'updated_at')),
        }),
    )

    def engagement_score(self, obj):
        total_feedback = obj.helpful_count + obj.not_helpful_count
        if total_feedback == 0:
            return "No feedback"
        percentage = (obj.helpful_count / total_feedback) * 100
        color = "green" if percentage >= 70 else "orange" if percentage >= 40 else "red"
        return format_html(
            '<span style="color: {}; font-weight: bold;">{:.0f}% Helpful</span>',
            color,
            percentage
        )
    engagement_score.short_description = 'Helpfulness'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('category')