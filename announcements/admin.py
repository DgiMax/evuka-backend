from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone

from .models import Announcement, AnnouncementReadStatus


class AnnouncementReadStatusInline(admin.TabularInline):
    model = AnnouncementReadStatus
    extra = 0
    readonly_fields = ("user", "is_read", "read_at")
    can_delete = False


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "status_colored",
        "creator",
        "organization",
        "audience_type",
        "publish_at",
        "published_at",
        "created_at",
    )

    list_filter = (
        "status",
        "audience_type",
        "organization",
        ("publish_at", admin.DateFieldListFilter),
        ("published_at", admin.DateFieldListFilter),
        ("created_at", admin.DateFieldListFilter),
    )

    search_fields = ("title", "content", "creator__username")
    autocomplete_fields = ("creator", "organization", "courses")

    readonly_fields = (
        "published_at",
        "approver",
        "created_at",
        "updated_at",
    )

    inlines = [AnnouncementReadStatusInline]

    fieldsets = (
        ("Basic Information", {
            "fields": ("title", "content")
        }),

        ("Context & Author", {
            "fields": ("creator", "organization"),
            "classes": ("collapse",),
        }),

        ("Audience", {
            "fields": ("audience_type", "courses"),
        }),

        ("Status & Scheduling", {
            "fields": ("status", "publish_at", "published_at", "approver"),
        }),

        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
        }),
    )

    filter_horizontal = ("courses",)

    def status_colored(self, obj):
        color_map = {
            "draft": "gray",
            "pending_approval": "orange",
            "scheduled": "blue",
            "published": "green",
            "archived": "red",
        }
        color = color_map.get(obj.status, "black")
        return format_html(
            "<span style='color: {}; font-weight: bold;'>{}</span>",
            color,
            obj.get_status_display()
        )
    status_colored.short_description = "Status"

    def save_model(self, request, obj, form, change):
        if obj.status == Announcement.Status.PUBLISHED and not obj.published_at:
            obj.published_at = timezone.now()
            obj.approver = request.user

        super().save_model(request, obj, form, change)


@admin.register(AnnouncementReadStatus)
class AnnouncementReadStatusAdmin(admin.ModelAdmin):
    list_display = ("user", "announcement", "is_read", "read_at")
    list_filter = ("is_read", ("read_at", admin.DateFieldListFilter))
    search_fields = ("user__username", "announcement__title")
    autocomplete_fields = ("user", "announcement")

    readonly_fields = ("read_at",)