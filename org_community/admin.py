from django.contrib import admin
from .models import OrgJoinRequest, AdvancedOrgInvitation, NegotiationLog


class NegotiationLogInline(admin.TabularInline):
    model = NegotiationLog
    extra = 0
    readonly_fields = ('actor', 'action', 'previous_value', 'new_value', 'note', 'created_at')
    can_delete = False

    def has_add_permission(self, request, obj):
        return False


@admin.register(AdvancedOrgInvitation)
class AdvancedOrgInvitationAdmin(admin.ModelAdmin):
    list_display = (
        'email', 'organization', 'invited_by',
        'gov_role', 'gov_status',
        'tutor_commission', 'tutor_status',
        'created_at'
    )
    list_filter = ('gov_status', 'tutor_status', 'organization', 'gov_role')
    search_fields = ('email', 'organization__name', 'invited_by__username')
    inlines = [NegotiationLogInline]

    fieldsets = (
        ('Invitation Details', {
            'fields': ('organization', 'invited_by', 'email')
        }),
        ('Governance Offer', {
            'fields': ('gov_role', 'gov_status')
        }),
        ('Teaching Offer', {
            'fields': ('is_tutor_invite', 'tutor_commission', 'tutor_status')
        }),
    )


@admin.register(OrgJoinRequest)
class OrgJoinRequestAdmin(admin.ModelAdmin):
    list_display = ('user', 'organization', 'desired_role', 'proposed_commission', 'status', 'created_at')
    list_filter = ('status', 'desired_role', 'organization')
    search_fields = ('user__username', 'user__email', 'organization__name')
    raw_id_fields = ('user', 'organization')