from django.contrib import admin
from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "recipient",
        "notification_type",
        "is_read_badge",
        "verb",
        "organization",
        "created_at",
    )
    list_filter = (
        "is_read",
        "notification_type",
        "organization",
        ("created_at", admin.DateFieldListFilter),
    )
    search_fields = (
        "recipient__username",
        "recipient__email",
        "verb",
    )
    autocomplete_fields = ("recipient", "organization")
    ordering = ("-created_at",)

    readonly_fields = (
        "content_type",
        "object_id",
        "content_object",
        "read_at",
        "created_at",
    )

    fieldsets = (
        ("Recipient & Context", {
            "fields": (("recipient", "organization"), "verb", "notification_type")
        }),
        ("Status", {
            "fields": (("is_read", "read_at"), "created_at"),
        }),
        ("Target Object (Generic Relation)", {
            "classes": ("collapse",),
            "description": "The specific object that triggered this notification.",
            "fields": ("content_object", "content_type", "object_id"),
        })
    )

    def is_read_badge(self, obj):
        from django.utils.html import format_html
        color = "#27ae60" if obj.is_read else "#e74c3c"
        text = "Read" if obj.is_read else "Unread"
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            text
        )

    is_read_badge.short_description = "Status"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("recipient", "organization")