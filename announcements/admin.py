from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from .models import Announcement, AnnouncementReadStatus


class AnnouncementReadStatusInline(admin.TabularInline):
    model = AnnouncementReadStatus
    extra = 0
    readonly_fields = ("user", "is_read", "read_at")
    can_delete = False
    show_change_link = True


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
    )
    list_filter = (
        "status",
        "audience_type",
        "organization",
        "created_at",
        "publish_at",
    )
    search_fields = ("title", "content", "creator__username", "creator__email")
    autocomplete_fields = ("creator", "organization", "courses")
    filter_horizontal = ("courses",)
    readonly_fields = ("published_at", "approver", "created_at", "updated_at")

    inlines = [AnnouncementReadStatusInline]

    fieldsets = (
        ("Content", {
            "fields": ("title", "content"),
        }),
        ("Ownership & Scope", {
            "fields": ("creator", "organization", "audience_type", "courses"),
        }),
        ("Status & Scheduling", {
            "fields": ("status", "publish_at", "published_at", "approver"),
        }),
        ("Metadata", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    def status_colored(self, obj):
        colors = {
            "draft": "#777",
            "pending_approval": "#f39c12",
            "scheduled": "#3498db",
            "published": "#27ae60",
            "archived": "#e74c3c",
        }
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            colors.get(obj.status, "#000"),
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
    list_filter = ("is_read", "read_at")
    search_fields = ("user__username", "user__email", "announcement__title")
    autocomplete_fields = ("user", "announcement")
    readonly_fields = ("read_at",)