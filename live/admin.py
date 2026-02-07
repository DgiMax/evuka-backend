from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html
from django.contrib import messages
from .models import LiveClass, LiveLesson, LessonResource

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
    can_delete = False

    def status_badge(self, obj):
        color_map = {
            "live": "#27ae60",
            "upcoming": "#2980b9",
            "completed": "#7f8c8d",
            "cancelled": "#c0392b"
        }
        return format_html(
            '<span style="color: white; background-color: {}; padding: 3px 8px; border-radius: 10px; font-size: 10px; font-weight: bold;">{}</span>',
            color_map.get(obj.status, "#000"),
            obj.status.upper()
        )
    status_badge.short_description = "Status"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('live_class')

@admin.register(LiveClass)
class LiveClassAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'status_pill',
        'course',
        'recurrence_type',
        'next_lesson_preview',
        'created_at'
    )
    list_filter = ('status', 'recurrence_type', 'timezone', 'created_at')
    search_fields = ('title', 'course__title', 'creator__username', 'creator__email')
    autocomplete_fields = ["course", "creator", "organization", "creator_profile"]
    readonly_fields = ("slug", "created_at", "updated_at")
    inlines = [LiveLessonInline]
    save_on_top = True

    fieldsets = (
        ("General Info", {
            "fields": ("title", "description", ("status", "slug"))
        }),
        ("Context & Ownership", {
            "fields": (("course", "organization"), ("creator", "creator_profile"))
        }),
        ("Scheduling Configuration", {
            "description": "Configuration for recurring or one-time sessions.",
            "fields": (
                "timezone",
                "recurrence_type",
                "recurrence_days",
                "single_session_start",
                "duration_minutes"
            ),
        }),
        ("Validity Period", {
            "fields": (("start_date", "end_date"),)
        }),
        ("Access Controls", {
            "fields": (("requires_auth", "allow_student_access"),)
        }),
        ("System Metadata", {
            "classes": ("collapse",),
            "fields": ("created_at", "updated_at")
        }),
    )

    def status_pill(self, obj):
        colors = {
            "draft": "#7f8c8d",
            "scheduled": "#2980b9",
            "completed": "#27ae60",
            "archived": "#c0392b"
        }
        return format_html(
            '<span style="color: white; background-color: {}; padding: 4px 10px; border-radius: 15px; font-weight: bold; font-size: 11px;">{}</span>',
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
            return next_lesson.start_datetime.strftime("%Y-%m-%d %H:%M")
        return "-"
    next_lesson_preview.short_description = "Next Session"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('course', 'creator')

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        try:
            from .services import LiveClassScheduler
            scheduler = LiveClassScheduler(obj)
            if change:
                scheduler.update_schedule()
                messages.info(request, "Schedule synchronized successfully.")
            else:
                scheduler.schedule_lessons(months_ahead=3)
                messages.success(request, "Initial sessions generated.")
        except ImportError:
            pass
        except Exception as e:
            messages.warning(request, f"Lesson generation error: {e}")

@admin.register(LiveLesson)
class LiveLessonAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'live_class',
        'start_datetime',
        'is_cancelled',
        'status_badge',
        'lock_status'
    )
    list_filter = ('is_cancelled', 'is_mic_locked', 'is_camera_locked', 'start_datetime')
    search_fields = ('title', 'live_class__title', 'chat_room_id')
    autocomplete_fields = ('live_class',)
    readonly_fields = ("chat_room_id", "created_at", "updated_at")
    inlines = [LessonResourceInline]
    date_hierarchy = 'start_datetime'

    actions = ['cancel_selected', 'activate_selected', 'reset_locks']

    fieldsets = (
        ("Session Details", {
            "fields": (("live_class", "title"), "description", "chat_room_id")
        }),
        ("Timing", {
            "fields": (("start_datetime", "end_datetime"), "extension_minutes")
        }),
        ("Controls", {
            "fields": (("is_cancelled", "is_mic_locked", "is_camera_locked"),)
        }),
        ("Participants", {
            "fields": ("attendees",),
            "classes": ("collapse",)
        }),
    )

    def status_badge(self, obj):
        color_map = {"live": "#27ae60", "upcoming": "#2980b9", "completed": "#7f8c8d", "cancelled": "#c0392b"}
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color_map.get(obj.status, "#000"), obj.status.upper()
        )
    status_badge.short_description = "Status"

    def lock_status(self, obj):
        locks = []
        if obj.is_mic_locked: locks.append("🎤🔒")
        if obj.is_camera_locked: locks.append("📷🔒")
        return " ".join(locks) if locks else "Open"
    lock_status.short_description = "Locks"

    @admin.action(description="Cancel selected sessions")
    def cancel_selected(self, request, queryset):
        queryset.update(is_cancelled=True)
        self.message_user(request, "Selected sessions cancelled.")

    @admin.action(description="Restore selected sessions")
    def activate_selected(self, request, queryset):
        queryset.update(is_cancelled=False)
        self.message_user(request, "Selected sessions restored.")

    @admin.action(description="Unlock all controls")
    def reset_locks(self, request, queryset):
        queryset.update(is_mic_locked=False, is_camera_locked=False)
        self.message_user(request, "Locks removed.")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('live_class')