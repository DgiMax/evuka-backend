from django.contrib import admin
from .models import ChatHistory

@admin.register(ChatHistory)
class ChatHistoryAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'course',
        'last_updated',
        'created_at',
    )
    search_fields = (
        'user__username',
        'course__title',
    )
    list_filter = (
        'course',
        'created_at',
    )
    readonly_fields = (
        'history_json',
        'created_at',
        'last_updated',
    )