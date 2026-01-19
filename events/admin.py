from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Event,
    EventRegistration,
    EventAttachment,
    EventLearningObjective,
    EventAgenda,
    EventRule
)

class EventAttachmentInline(admin.TabularInline):
    model = EventAttachment
    extra = 1

class EventAgendaInline(admin.TabularInline):
    model = EventAgenda
    extra = 1

class EventLearningObjectiveInline(admin.TabularInline):
    model = EventLearningObjective
    extra = 1

class EventRuleInline(admin.TabularInline):
    model = EventRule
    extra = 1

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "event_status_badge",
        "event_type",
        "start_time",
        "organizer",
        "registrations_count",
    )
    list_filter = ("event_status", "event_type", "start_time", "is_paid")
    search_fields = ("title", "organizer__username", "organizer__email")
    prepopulated_fields = {"slug": ("title",)}
    inlines = [
        EventAgendaInline,
        EventLearningObjectiveInline,
        EventRuleInline,
        EventAttachmentInline,
    ]
    readonly_fields = ("chat_room_id", "created_at", "updated_at")

    fieldsets = (
        ("Basic Info", {
            "fields": ("course", "title", "slug", "organizer", "banner_image")
        }),
        ("Status & Type", {
            "fields": ("event_status", "event_type", "who_can_join")
        }),
        ("Schedule & Location", {
            "fields": ("start_time", "end_time", "timezone", "location", "meeting_link", "chat_room_id")
        }),
        ("Description", {
            "fields": ("overview", "description")
        }),
        ("Registration Settings", {
            "fields": (
                "is_paid",
                "price",
                "currency",
                "max_attendees",
                "registration_open",
                "registration_deadline",
            )
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at")
        }),
    )

    def event_status_badge(self, obj):
        colors = {
            "draft": "#f39c12",
            "pending_approval": "#e67e22",
            "approved": "#27ae60",
            "cancelled": "#c0392b",
            "completed": "#7f8c8d",
            "ongoing": "#3498db",
        }
        color = colors.get(obj.event_status, "#333")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 10px;">{}</span>',
            color,
            obj.get_event_status_display(),
        )
    event_status_badge.short_description = "Status"

    def registrations_count(self, obj):
        return obj.registrations.count()
    registrations_count.short_description = "Attendees"


@admin.register(EventRegistration)
class EventRegistrationAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "event",
        "status_badge",
        "ticket_id_short",
        "payment_status",
        "registered_at",
    )
    list_filter = ("status", "payment_status", "registered_at", "event__event_type")
    search_fields = (
        "user__username",
        "user__email",
        "event__title",
        "ticket_id",
        "payment_reference",
    )
    readonly_fields = (
        "ticket_id",
        "ticket_qr_code_preview",
        "registered_at",
        "updated_at",
    )

    fieldsets = (
        ("Registration Info", {
            "fields": ("event", "user", "status", "registered_at")
        }),
        ("Payment", {
            "fields": ("payment_status", "payment_reference")
        }),
        ("Ticket Details", {
            "fields": ("ticket_id", "ticket_qr_code_preview", "checked_in_at")
        }),
    )

    def status_badge(self, obj):
        colors = {
            "registered": "green",
            "attended": "blue",
            "cancelled": "red",
        }
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            colors.get(obj.status, "black"),
            obj.get_status_display(),
        )
    status_badge.short_description = "Status"

    def ticket_id_short(self, obj):
        return str(obj.ticket_id)[:8].upper()
    ticket_id_short.short_description = "Ticket ID"

    def ticket_qr_code_preview(self, obj):
        if obj.ticket_qr_code:
            return format_html(
                '<img src="{}" width="150" height="150" style="border: 1px solid #ddd; padding: 5px;" />',
                obj.ticket_qr_code.url
            )
        return "No QR Code generated"
    ticket_qr_code_preview.short_description = "QR Code"