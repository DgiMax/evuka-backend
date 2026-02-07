from django.contrib import admin
from django.utils.html import format_html
from .models import OrgJoinRequest, AdvancedOrgInvitation, NegotiationLog

class NegotiationLogInline(admin.TabularInline):
    model = NegotiationLog
    extra = 0
    readonly_fields = ('actor', 'action', 'previous_value', 'new_value', 'note', 'created_at')
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False

@admin.register(AdvancedOrgInvitation)
class AdvancedOrgInvitationAdmin(admin.ModelAdmin):
    list_display = (
        'email',
        'organization',
        'gov_role_badge',
        'gov_status_pill',
        'tutor_info',
        'tutor_status_pill',
        'created_at'
    )
    list_filter = (
        'gov_status',
        'tutor_status',
        'gov_role',
        'is_tutor_invite',
        'organization',
        ('created_at', admin.DateFieldListFilter)
    )
    search_fields = ('email', 'organization__name', 'invited_by__username', 'invited_by__email')
    autocomplete_fields = ('organization', 'invited_by')
    readonly_fields = ('id', 'created_at', 'updated_at')
    inlines = [NegotiationLogInline]
    save_on_top = True

    fieldsets = (
        ('Invitation Basics', {
            'fields': (('organization', 'invited_by'), 'email', 'id')
        }),
        ('Governance & Access', {
            'fields': (('gov_role', 'gov_status'),)
        }),
        ('Tutor Partnership', {
            'fields': ('is_tutor_invite', ('tutor_commission', 'tutor_status'))
        }),
        ('System Metadata', {
            'classes': ('collapse',),
            'fields': ('created_at', 'updated_at')
        }),
    )

    def gov_role_badge(self, obj):
        return format_html('<span style="font-weight: bold; text-transform: uppercase;">{}</span>', obj.gov_role)
    gov_role_badge.short_description = "Role"

    def gov_status_pill(self, obj):
        colors = {'pending': '#f39c12', 'negotiating': '#3498db', 'accepted': '#27ae60', 'rejected': '#e74c3c', 'revoked': '#7f8c8d'}
        return format_html(
            '<span style="color: white; background-color: {}; padding: 3px 8px; border-radius: 10px; font-size: 10px;">{}</span>',
            colors.get(obj.gov_status, '#333'), obj.get_gov_status_display()
        )
    gov_status_pill.short_description = "Gov Status"

    def tutor_status_pill(self, obj):
        if not obj.is_tutor_invite: return "-"
        colors = {'pending': '#f39c12', 'negotiating': '#3498db', 'accepted': '#27ae60', 'rejected': '#e74c3c', 'revoked': '#7f8c8d'}
        return format_html(
            '<span style="color: white; background-color: {}; padding: 3px 8px; border-radius: 10px; font-size: 10px;">{}</span>',
            colors.get(obj.tutor_status, '#333'), obj.get_tutor_status_display()
        )
    tutor_status_pill.short_description = "Tutor Status"

    def tutor_info(self, obj):
        if obj.is_tutor_invite:
            return f"{obj.tutor_commission}%"
        return "N/A"
    tutor_info.short_description = "Comm %"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('organization', 'invited_by')

@admin.register(OrgJoinRequest)
class OrgJoinRequestAdmin(admin.ModelAdmin):
    list_display = ('user', 'organization', 'desired_role', 'commission_display', 'status_pill', 'created_at')
    list_filter = ('status', 'desired_role', 'organization', ('created_at', admin.DateFieldListFilter))
    search_fields = ('user__username', 'user__email', 'organization__name')
    autocomplete_fields = ('user', 'organization')
    readonly_fields = ('created_at', 'updated_at')

    def status_pill(self, obj):
        colors = {'pending': '#f39c12', 'approved': '#27ae60', 'rejected': '#e74c3c'}
        return format_html(
            '<span style="color: white; background-color: {}; padding: 4px 10px; border-radius: 12px; font-weight: bold; font-size: 11px;">{}</span>',
            colors.get(obj.status, '#333'), obj.get_status_display()
        )
    status_pill.short_description = "Status"

    def commission_display(self, obj):
        if obj.desired_role == 'tutor':
            return f"{obj.proposed_commission}%"
        return "-"
    commission_display.short_description = "Proposed Comm."

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'organization')

@admin.register(NegotiationLog)
class NegotiationLogAdmin(admin.ModelAdmin):
    list_display = ('invitation', 'actor', 'action', 'created_at')
    list_filter = ('action', 'created_at')
    search_fields = ('invitation__email', 'actor__username', 'note')
    autocomplete_fields = ('invitation', 'actor')