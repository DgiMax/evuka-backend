from django.contrib import admin
from django import forms
from django.utils.html import format_html
from django.utils import timezone
from .models import (
    Event,
    EventRegistration,
    EventAttachment,
    EventLearningObjective,
    EventAgenda,
    EventRule
)


# --- Inlines ---

class EventAttachmentInline(admin.TabularInline):
    model = EventAttachment
    extra = 1
    fields = ("file", "uploaded_by", "uploaded_at")
    readonly_fields = ("uploaded_at",)
    autocomplete_fields = ("uploaded_by",)


class EventAgendaInline(admin.TabularInline):
    model = EventAgenda
    extra = 1
    fields = ("order", "time", "title", "description")
    ordering = ("order",)


class EventLearningObjectiveInline(admin.TabularInline):
    model = EventLearningObjective
    extra = 1


class EventRuleInline(admin.TabularInline):
    model = EventRule
    extra = 1


# --- Admin Classes ---

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "event_status_badge",
        "event_type",
        "start_time",
        "organizer",
        "registrations_count",
        "is_paid",
    )
    list_filter = (
        "event_status",
        "event_type",
        "who_can_join",
        "is_paid",
        ("start_time", admin.DateFieldListFilter)
    )
    search_fields = (
        "title",
        "slug",
        "organizer__username",
        "organizer__email",
        "course__title"
    )
    prepopulated_fields = {"slug": ("title",)}
    autocomplete_fields = ("course", "organizer")
    save_on_top = True

    readonly_fields = ("chat_room_id", "created_at", "updated_at")

    inlines = [
        EventLearningObjectiveInline,
        EventAgendaInline,
        EventRuleInline,
        EventAttachmentInline,
    ]

    fieldsets = (
        ("Core Information", {
            "fields": ("course", "title", "slug", "organizer", "banner_image")
        }),
        ("Status & Audience", {
            "fields": (("event_status", "event_type"), "who_can_join")
        }),
        ("Schedule & Venue", {
            "fields": (("start_time", "end_time"), "timezone", "location", "meeting_link", "chat_room_id")
        }),
        ("Content", {
            "fields": ("overview", "description")
        }),
        ("Registration & Logistics", {
            "fields": (
                ("is_paid", "price", "currency"),
                ("max_attendees", "registration_open"),
                "registration_deadline",
            )
        }),
        ("Permissions & Locks", {
            "description": "Control attendee interactions during the event.",
            "fields": (("mic_locked", "camera_locked", "screen_locked"),)
        }),
        ("System Metadata", {
            "classes": ("collapse",),
            "fields": ("created_at", "updated_at")
        }),
    )

    def event_status_badge(self, obj):
        colors = {
            "draft": "#7f8c8d",
            "pending_approval": "#e67e22",
            "approved": "#27ae60",
            "scheduled": "#2980b9",
            "ongoing": "#f1c40f",
            "completed": "#2c3e50",
            "cancelled": "#c0392b",
            "postponed": "#9b59b6",
        }
        color = colors.get(obj.event_status, "#333")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 4px 10px; border-radius: 12px; font-weight: bold; font-size: 11px;">{}</span>',
            color,
            obj.get_event_status_display(),
        )

    event_status_badge.short_description = "Status"

    def registrations_count(self, obj):
        return obj.registrations.count()

    registrations_count.short_description = "Attendees"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("course", "organizer")


@admin.register(EventRegistration)
class EventRegistrationAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "event",
        "status_badge",
        "payment_status_badge",
        "ticket_id_short",
        "registered_at",
    )
    list_filter = (
        "status",
        "payment_status",
        ("registered_at", admin.DateFieldListFilter),
        "event__event_type"
    )
    search_fields = (
        "user__username",
        "user__email",
        "event__title",
        "ticket_id",
        "payment_reference",
    )
    autocomplete_fields = ("event", "user")
    readonly_fields = (
        "ticket_id",
        "ticket_qr_code_preview",
        "registered_at",
        "updated_at",
        "checked_in_at"
    )

    fieldsets = (
        ("Attendee Info", {
            "fields": ("event", "user", "status", "checked_in_at")
        }),
        ("Financials", {
            "fields": ("payment_status", "payment_reference")
        }),
        ("Ticket Information", {
            "fields": ("ticket_id", "ticket_qr_code_preview")
        }),
        ("Timestamps", {
            "classes": ("collapse",),
            "fields": ("registered_at", "updated_at")
        }),
    )

    def status_badge(self, obj):
        colors = {"registered": "#27ae60", "attended": "#2980b9", "cancelled": "#c0392b"}
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            colors.get(obj.status, "#000"),
            obj.get_status_display(),
        )

    status_badge.short_description = "Reg Status"

    def payment_status_badge(self, obj):
        colors = {"pending": "#e67e22", "paid": "#27ae60", "free": "#7f8c8d"}
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            colors.get(obj.payment_status, "#000"),
            obj.get_payment_status_display(),
        )

    payment_status_badge.short_description = "Payment"

    def ticket_id_short(self, obj):
        return str(obj.ticket_id)[:8].upper()

    ticket_id_short.short_description = "Ticket ID"

    def ticket_qr_code_preview(self, obj):
        if obj.ticket_qr_code:
            return format_html(
                '<div style="background: white; display: inline-block; padding: 10px; border: 1px solid #ccc;">'
                '<img src="{}" width="150" height="150" />'
                '</div>',
                obj.ticket_qr_code.url
            )
        return "No QR Code generated"

    ticket_qr_code_preview.short_description = "QR Code Preview"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user", "event")


@admin.register(EventAttachment)
class EventAttachmentAdmin(admin.ModelAdmin):
    list_display = ("event", "file", "uploaded_by", "uploaded_at")
    list_filter = ("uploaded_at", "event")
    autocomplete_fields = ("event", "uploaded_by")