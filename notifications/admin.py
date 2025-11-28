from django.contrib import admin
from .models import Notification

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "recipient",
        "notification_type",
        "is_read",
        "verb",
        "organization",
        "created_at",
    )
    list_filter = (
        "is_read",
        "notification_type",
        "organization",
        "created_at",
    )
    search_fields = (
        "recipient__username",
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

    # Grouping GFK fields for better readability
    fieldsets = (
        (None, {
            "fields": ("recipient", "verb", "notification_type", "organization")
        }),
        ("Status & Read Data", {
            "fields": ("is_read", "read_at", "created_at"),
        }),
        ("Source Object (Read Only)", {
            # content_object is the GenericForeignKey field itself
            "fields": ("content_object", "content_type", "object_id"),
            "classes": ("collapse",)
        })
    )