from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Organization, OrgMembership, OrgCategory,
    OrgLevel, GuardianLink
)
from .models_finance import TutorAgreement, PendingEarning

class OrgMembershipInline(admin.TabularInline):
    model = OrgMembership
    extra = 0
    autocomplete_fields = ('user', 'level')
    fields = ('user', 'role', 'level', 'is_active', 'payment_status')

@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('name', 'status_badge', 'org_type', 'membership_info', 'payout_frequency', 'approved')
    list_filter = ('status', 'approved', 'org_type', 'payout_frequency')
    search_fields = ('name', 'slug', 'description')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [OrgMembershipInline]
    save_on_top = True

    fieldsets = (
        ('General Information', {
            'fields': (('name', 'org_type'), ('status', 'approved'), 'slug', 'description', 'logo')
        }),
        ('Membership Configuration', {
            'fields': (('membership_price', 'membership_period'), 'membership_duration_value'),
            'description': 'Define how users pay for and access the organization.'
        }),
        ('Payout & Distribution', {
            'fields': (('payout_frequency', 'payout_anchor_day'), 'auto_distribute'),
            'description': 'Configure tutor payment schedules and automation.'
        }),
        ('Branding & Customization', {
            'classes': ('collapse',),
            'fields': ('branding', 'policies')
        }),
    )

    def status_badge(self, obj):
        colors = {
            "draft": "#7f8c8d",
            "pending_approval": "#f39c12",
            "approved": "#27ae60",
            "suspended": "#e74c3c",
            "archived": "#2c3e50",
        }
        return format_html(
            '<span style="color: white; background-color: {}; padding: 3px 10px; border-radius: 12px; font-weight: bold; font-size: 11px;">{}</span>',
            colors.get(obj.status, "#333"), obj.get_status_display()
        )
    status_badge.short_description = "Status"

    def membership_info(self, obj):
        return f"{obj.membership_price} / {obj.get_membership_period_display()}"
    membership_info.short_description = "Membership"

@admin.register(OrgMembership)
class OrgMembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'organization', 'role_badge', 'level', 'is_active', 'payment_status', 'date_joined')
    list_filter = ('role', 'is_active', 'payment_status', 'organization', 'level')
    search_fields = ('user__username', 'user__email', 'organization__name')
    autocomplete_fields = ('user', 'organization', 'level', 'subjects')
    filter_horizontal = ('subjects',)
    readonly_fields = ('date_joined',)

    def role_badge(self, obj):
        return format_html('<span style="font-weight: bold; text-transform: uppercase; font-size: 10px;">{}</span>', obj.role)
    role_badge.short_description = "Role"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'organization', 'level')

@admin.register(TutorAgreement)
class TutorAgreementAdmin(admin.ModelAdmin):
    list_display = ('user', 'organization', 'commission_percent', 'is_active', 'signed_by_user')
    list_filter = ('is_active', 'organization', 'signed_by_user')
    search_fields = ('user__username', 'organization__name')
    autocomplete_fields = ('user', 'organization')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'organization')

@admin.register(PendingEarning)
class PendingEarningAdmin(admin.ModelAdmin):
    list_display = ('tutor', 'organization', 'amount', 'is_cleared', 'created_at')
    list_filter = ('is_cleared', 'organization', ('created_at', admin.DateFieldListFilter))
    search_fields = ('tutor__username', 'organization__name', 'source_order_item__order__order_number')
    autocomplete_fields = ('tutor', 'organization', 'source_order_item')
    date_hierarchy = 'created_at'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('tutor', 'organization', 'source_order_item')

@admin.register(OrgCategory)
class OrgCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'created_at')
    list_filter = ('organization',)
    search_fields = ('name', 'organization__name')
    autocomplete_fields = ('organization',)

@admin.register(OrgLevel)
class OrgLevelAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'order')
    list_filter = ('organization',)
    search_fields = ('name', 'organization__name')
    autocomplete_fields = ('organization',)
    ordering = ('organization', 'order')

@admin.register(GuardianLink)
class GuardianLinkAdmin(admin.ModelAdmin):
    list_display = ('parent', 'student', 'organization', 'relationship')
    search_fields = ('parent__username', 'student__username', 'organization__name')
    autocomplete_fields = ('parent', 'student', 'organization')