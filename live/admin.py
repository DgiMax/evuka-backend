from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html
from django.contrib import messages
from .models import LiveClass, LiveLesson, LessonResource
from .services import LiveClassScheduler  # Ensure you import your service


class LessonResourceInline(admin.TabularInline):
    model = LessonResource
    extra = 1
    fields = ('title', 'file', 'uploaded_at')
    readonly_fields = ('uploaded_at',)


class LiveLessonInline(admin.TabularInline):
    model = LiveLesson
    extra = 0
    show_change_link = True
    fields = ('title', 'start_datetime', 'end_datetime', 'is_cancelled', 'status_badge')
    readonly_fields = ('status_badge',)
    ordering = ('start_datetime',)
    can_delete = False  # Prevent accidental deletion from parent view

    def status_badge(self, obj):
        color_map = {
            "live": "green",
            "upcoming": "blue",
            "completed": "gray",
            "cancelled": "red"
        }
        color = color_map.get(obj.status, "black")
        return format_html(
            '<span style="color: white; background-color: {}; padding: 3px 8px; border-radius: 10px; font-size: 10px;">{}</span>',
            color, obj.status.upper()
        )

    status_badge.short_description = "Status"

    def get_queryset(self, request):
        # Only show future or recent lessons to keep the interface clean
        qs = super().get_queryset(request)
        cutoff = timezone.now() - timezone.timedelta(days=7)
        return qs.filter(start_datetime__gte=cutoff)


@admin.register(LiveClass)
class LiveClassAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'course_link',
        'recurrence_type',
        'timezone_info',
        'next_lesson_preview',
        'status_pill'
    )
    list_filter = ('status', 'recurrence_type', 'timezone', 'created_at')
    search_fields = ('title', 'course__title', 'creator__username', 'creator__email')
    inlines = [LiveLessonInline]

    fieldsets = (
        ("General Info", {
            "fields": ("title", "description", "slug", "status")
        }),
        ("Context", {
            "fields": ("course", "organization", "creator", "creator_profile")
        }),
        ("Scheduling Configuration", {
            "fields": (
                "timezone",
                "recurrence_type",
                "recurrence_days",
                "single_session_start",
                "duration_minutes"
            ),
            "description": "Changing these settings will trigger a regeneration of future lessons."
        }),
        ("Validity Period", {
            "fields": ("start_date", "end_date")
        }),
        ("Permissions", {
            "fields": ("requires_auth", "allow_student_access")
        }),
    )

    readonly_fields = ("slug",)
    autocomplete_fields = ["course", "creator"]  # Assumes these are registered in Admin

    def save_model(self, request, obj, form, change):
        """
        Overriding save to ensure the Schedule Service runs even when
        edited by an Admin.
        """
        super().save_model(request, obj, form, change)

        # Trigger the service to sync lessons
        try:
            scheduler = LiveClassScheduler(obj)
            if change:
                scheduler.update_schedule()
                messages.info(request, f"Schedule updated and future lessons regenerated for '{obj.title}'.")
            else:
                scheduler.schedule_lessons(months_ahead=3)
                messages.success(request, f"Live Class created and initial lessons generated for '{obj.title}'.")
        except Exception as e:
            messages.warning(request, f"Class saved, but lesson generation failed: {e}")

    # --- Custom Column Methods ---

    def course_link(self, obj):
        return obj.course.title

    course_link.short_description = "Course"

    def timezone_info(self, obj):
        return f"{obj.timezone}"

    timezone_info.short_description = "Region/TZ"

    def status_pill(self, obj):
        colors = {
            "draft": "#f39c12",
            "scheduled": "#3498db",
            "completed": "#95a5a6",
            "archived": "#7f8c8d"
        }
        return format_html(
            '<span style="color: white; background-color: {}; padding: 5px 10px; border-radius: 15px; font-weight: bold;">{}</span>',
            colors.get(obj.status, "#333"),
            obj.get_status_display()
        )

    status_pill.short_description = "Status"

    def next_lesson_preview(self, obj):
        next_lesson = obj.lessons.filter(
            start_datetime__gte=timezone.now(),
            is_cancelled=False
        ).order_by('start_datetime').first()

        if next_lesson:
            return next_lesson.start_datetime.strftime("%Y-%m-%d %H:%M UTC")
        return "-"

    next_lesson_preview.short_description = "Next Session"


@admin.register(LiveLesson)
class LiveLessonAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'live_class',
        'start_datetime',
        'duration_display',
        'is_cancelled',
        'status_display',
        'lock_status'
    )
    list_filter = (
        'is_cancelled',
        'start_datetime',
        'live_class__timezone',
        'is_mic_locked'
    )
    search_fields = ('title', 'live_class__title', 'chat_room_id')
    date_hierarchy = 'start_datetime'
    inlines = [LessonResourceInline]

    actions = ['cancel_lessons', 'activate_lessons', 'unlock_all_controls']

    fieldsets = (
        ("Lesson Details", {
            "fields": ("live_class", "title", "description", "chat_room_id")
        }),
        ("Timing (UTC)", {
            "fields": ("start_datetime", "end_datetime", "extension_minutes")
        }),
        ("State & Controls", {
            "fields": ("is_cancelled", "is_mic_locked", "is_camera_locked")
        }),
    )

    readonly_fields = ("chat_room_id", "live_class")

    # --- Custom Actions ---

    @admin.action(description="Cancel selected lessons")
    def cancel_lessons(self, request, queryset):
        updated = queryset.update(is_cancelled=True)
        self.message_user(request, f"{updated} lessons marked as cancelled.")

    @admin.action(description="Re-activate selected lessons")
    def activate_lessons(self, request, queryset):
        updated = queryset.update(is_cancelled=False)
        self.message_user(request, f"{updated} lessons restored.")

    @admin.action(description="Unlock Mic and Camera")
    def unlock_all_controls(self, request, queryset):
        queryset.update(is_mic_locked=False, is_camera_locked=False)
        self.message_user(request, "Permissions reset for selected lessons.")

    # --- Column Methods ---

    def status_display(self, obj):
        return obj.status.upper()

    status_display.short_description = "Current State"

    def duration_display(self, obj):
        duration = obj.end_datetime - obj.start_datetime
        minutes = int(duration.total_seconds() / 60)
        return f"{minutes} min"

    duration_display.short_description = "Duration"

    def lock_status(self, obj):
        icons = []
        if obj.is_mic_locked:
            icons.append("🎤🔒")
        if obj.is_camera_locked:
            icons.append("📷🔒")
        return " ".join(icons) if icons else "Open"

    lock_status.short_description = "Locks"