from django.contrib import admin
from .models import (
    Organization, OrgMembership, OrgCategory,
    OrgLevel, GuardianLink
)
from .models_finance import TutorAgreement, PendingEarning


class OrgMembershipInline(admin.TabularInline):
    model = OrgMembership
    extra = 0
    raw_id_fields = ('user',)


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('name', 'org_type', 'status', 'approved', 'payout_frequency', 'auto_distribute')
    list_filter = ('status', 'approved', 'org_type', 'payout_frequency')
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [OrgMembershipInline]
    fieldsets = (
        ('Basic Info', {
            'fields': ('name', 'slug', 'org_type', 'status', 'approved', 'description', 'logo')
        }),
        ('Membership Settings', {
            'fields': ('membership_price', 'membership_period', 'membership_duration_value')
        }),
        ('Financial Settings', {
            'fields': ('payout_frequency', 'payout_anchor_day', 'auto_distribute'),
            'description': 'Controls how and when tutors get paid.'
        }),
        ('Json Data', {
            'fields': ('branding', 'policies'),
            'classes': ('collapse',)
        }),
    )


@admin.register(OrgMembership)
class OrgMembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'organization', 'role', 'is_active', 'payment_status', 'date_joined')
    list_filter = ('role', 'is_active', 'payment_status', 'organization')
    search_fields = ('user__username', 'user__email', 'organization__name')
    raw_id_fields = ('user', 'organization')


@admin.register(TutorAgreement)
class TutorAgreementAdmin(admin.ModelAdmin):
    list_display = ('user', 'organization', 'commission_percent', 'is_active', 'signed_by_user')
    list_filter = ('is_active', 'organization', 'signed_by_user')
    search_fields = ('user__username', 'organization__name')
    raw_id_fields = ('user', 'organization')


@admin.register(PendingEarning)
class PendingEarningAdmin(admin.ModelAdmin):
    list_display = ('tutor', 'organization', 'amount', 'is_cleared', 'created_at')
    list_filter = ('is_cleared', 'organization')
    search_fields = ('tutor__username', 'organization__name', 'source_order_item__order__order_number')
    date_hierarchy = 'created_at'
    raw_id_fields = ('tutor', 'organization', 'source_order_item')


@admin.register(OrgCategory)
class OrgCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'created_at')
    list_filter = ('organization',)
    search_fields = ('name',)


@admin.register(OrgLevel)
class OrgLevelAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'order')
    list_filter = ('organization',)
    search_fields = ('name',)
    ordering = ('organization', 'order')


@admin.register(GuardianLink)
class GuardianLinkAdmin(admin.ModelAdmin):
    list_display = ('parent', 'student', 'organization', 'relationship')
    search_fields = ('parent__username', 'student__username', 'organization__name')