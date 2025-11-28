from django.contrib import admin
from .models import LiveClass, LiveLesson


@admin.register(LiveClass)
class LiveClassAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "creator",
        "organization",
        "status",
        "start_date",
        "lesson_duration",
        "recurrence_type",
        "created_at",
    )
    readonly_fields = ("slug", "meeting_link", "created_at", "updated_at", "display_jitsi_room_name")
    autocomplete_fields = ("organization", "creator", "course")
    list_filter = (
        "status",
        "recurrence_type",
        "organization",
        "created_at",
    )
    search_fields = (
        "title",
        "description",
        "creator__username",
        "organization__name",
    )
    ordering = ("-created_at",)
    date_hierarchy = "start_date"

    fieldsets = (
        (
            "General Information",
            {
                "fields": (
                    "title",
                    "slug",
                    "description",
                    "organization",
                    "creator",
                    "course",
                )
            },
        ),
        (
            "Scheduling & Recurrence",
            {
                "fields": (
                    "start_date",
                    "end_date",
                    "lesson_duration",
                    "recurrence_type",
                    "recurrence_days",
                    "recurrence_update_mode",
                ),
            },
        ),
        (
            "Jitsi Configuration",
            {
                "fields": (
                    "meeting_link",
                    "display_jitsi_room_name",
                    "requires_auth",
                    "allow_student_access",
                ),
            },
        ),
        (
            "Status & Metadata",
            {"fields": ("status", "created_at", "updated_at")},
        ),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser:
            active_org = getattr(request, "active_organization", None)
            if active_org:
                return qs.filter(organization=active_org)
        return qs

    def display_jitsi_room_name(self, obj):
        return obj.get_jitsi_room_name()
    display_jitsi_room_name.short_description = "Jitsi Room Name"


@admin.register(LiveLesson)
class LiveLessonAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "live_class",
        "date",
        "start_time",
        "end_time",
        "jitsi_room_name",
    )
    readonly_fields = ("jitsi_meeting_link", "jitsi_room_name",)
    autocomplete_fields = ("live_class",)
    list_filter = ("live_class__organization", "date")
    search_fields = ("title", "live_class__title", "live_class__creator__username")
    ordering = ("date", "start_time")

    fieldsets = (
        (
            "Lesson Details",
            {
                "fields": (
                    "live_class",
                    "title",
                    "description",
                    "date",
                    "start_time",
                    "end_time",
                )
            },
        ),
        (
            "Jitsi Meeting",
            {
                "fields": ("jitsi_room_name", "jitsi_meeting_link"),
            },
        ),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser:
            active_org = getattr(request, "active_organization", None)
            if active_org:
                return qs.filter(live_class__organization=active_org)
        return qs