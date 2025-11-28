from django.contrib import admin
from .models import (
    Event,
    EventRegistration,
    EventAttachment,
    EventAgenda,
    EventLearningObjective,
    EventRule,
)


class EventRegistrationInline(admin.TabularInline):
    model = EventRegistration
    extra = 0
    readonly_fields = ("user", "registered_at")


class EventAttachmentInline(admin.TabularInline):
    model = EventAttachment
    extra = 0
    readonly_fields = ("uploaded_by", "uploaded_at")


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


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "course",
        "event_type",
        "is_paid",
        "registration_open",
        "start_time",
    )
    list_filter = ("event_type", "is_paid", "registration_open", "course")
    search_fields = ("title", "course__title", "organizer__username")
    prepopulated_fields = {"slug": ("title",)}
    inlines = [
        EventAgendaInline,
        EventLearningObjectiveInline,
        EventRuleInline,
        EventAttachmentInline,
        EventRegistrationInline,
    ]


@admin.register(EventRegistration)
class EventRegistrationAdmin(admin.ModelAdmin):
    list_display = ("event", "user", "status", "payment_status", "registered_at")
    list_filter = ("status", "payment_status")
    search_fields = ("user__username", "event__title")


@admin.register(EventAttachment)
class EventAttachmentAdmin(admin.ModelAdmin):
    list_display = ("event", "file", "uploaded_by", "uploaded_at")
    list_filter = ("event",)


@admin.register(EventAgenda)
class EventAgendaAdmin(admin.ModelAdmin):
    list_display = ("event", "order", "time", "title")
    ordering = ("event", "order")


@admin.register(EventLearningObjective)
class EventLearningObjectiveAdmin(admin.ModelAdmin):
    list_display = ("event", "text")


@admin.register(EventRule)
class EventRuleAdmin(admin.ModelAdmin):
    list_display = ("event", "title")