from django.contrib import admin
from .models import OrgJoinRequest, OrgInvitation


@admin.register(OrgJoinRequest)
class OrgJoinRequestAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'organization',
        'status',
        'created_at',
        'updated_at',
    )
    list_filter = ('status', 'organization', 'created_at')
    search_fields = ('user__username', 'organization__name')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)
    autocomplete_fields = ('user', 'organization')
    fieldsets = (
        (None, {
            'fields': ('user', 'organization', 'message', 'status')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
        }),
    )


@admin.register(OrgInvitation)
class OrgInvitationAdmin(admin.ModelAdmin):
    list_display = (
        'organization',
        'invited_user',
        'invited_by',
        'role',
        'status',
        'created_at',
        'updated_at',
    )
    list_filter = ('status', 'role', 'organization', 'created_at')
    search_fields = (
        'organization__name',
        'invited_user__username',
        'invited_by__username',
    )
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)
    autocomplete_fields = ('organization', 'invited_user', 'invited_by')
    fieldsets = (
        (None, {
            'fields': (
                'organization',
                'invited_user',
                'invited_by',
                'role',
                'status',
            )
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
        }),
    )