from django.contrib import admin
from django import forms
from django.utils.html import format_html
from .models import (
    Organization, OrgMembership, GuardianLink,
    OrgCategory, OrgLevel
)


class OrgCategoryInline(admin.TabularInline):
    """Allows defining Categories/Subjects within the Organization view."""
    model = OrgCategory
    extra = 1
    fields = ("name", "description", "thumbnail")
    show_change_link = True


class OrgLevelInline(admin.TabularInline):
    """Allows defining Levels/Grades within the Organization view."""
    model = OrgLevel
    extra = 1
    fields = ("name", "order", "description")
    ordering = ("order",)
    show_change_link = True


class OrgMembershipInline(admin.TabularInline):
    """Allows managing members and roles within the Organization view."""
    model = OrgMembership
    extra = 0
    fields = (
        "user", "role", "is_active", "payment_status", "expires_at",
        "level", "get_subjects_display"
    )
    readonly_fields = ("get_subjects_display", "expires_at")
    autocomplete_fields = ("user", "level", "subjects")
    verbose_name = "Organization Member"

    @admin.display(description="Subjects")
    def get_subjects_display(self, obj):
        return ", ".join([s.name for s in obj.subjects.all()])


class OrganizationAdminForm(forms.ModelForm):
    class Meta:
        model = Organization
        fields = "__all__"
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "branding": forms.Textarea(attrs={"rows": 3}),
            "policies": forms.Textarea(attrs={"rows": 3}),
        }

@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    form = OrganizationAdminForm
    list_display = (
        "name", "org_type", "approved", "membership_period",
        "membership_price", "get_member_count", "created_at"
    )
    list_filter = ("org_type", "approved", "membership_period")
    search_fields = ("name", "description", "slug")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at", "updated_at")

    inlines = [OrgCategoryInline, OrgLevelInline, OrgMembershipInline]

    fieldsets = (
        ("General Information", {
            "fields": ("name", "slug", "org_type", "description", "approved")
        }),
        ("Branding & Policies", {
            "fields": ("branding", "policies")
        }),
        ("Membership & Pricing", {
            "fields": (
                "membership_period", "membership_price",
                "membership_duration_value",
            ),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at")
        })
    )

    @admin.display(description="Members")
    def get_member_count(self, obj):
        return obj.memberships.filter(is_active=True).count()


@admin.register(OrgMembership)
class OrgMembershipAdmin(admin.ModelAdmin):
    list_display = (
        "user", "organization", "role", "is_active", "payment_status",
        "expires_at", "date_joined"
    )
    list_filter = ("role", "is_active", "payment_status", "organization")
    search_fields = (
        "user__email", "user__username", "organization__name",
        "level__name", "subjects__name"
    )
    autocomplete_fields = ("user", "organization", "level", "subjects")
    readonly_fields = ("date_joined", "expires_at")
    filter_horizontal = ("subjects",)

    fieldsets = (
        ("User & Organization", {
            "fields": ("user", "organization", "role", "is_active")
        }),
        ("Payment & Expiry", {
            "fields": ("payment_status", "expires_at", "date_joined"),
        }),
        ("Taxonomy Mapping", {
            "fields": ("level", "subjects"),
        })
    )


@admin.register(GuardianLink)
class GuardianLinkAdmin(admin.ModelAdmin):
    list_display = ("parent", "student", "organization", "relationship")
    list_filter = ("organization", "relationship")
    search_fields = ("parent__username", "student__username", "organization__name")
    autocomplete_fields = ("parent", "student", "organization")
    list_editable = ("relationship",)


@admin.register(OrgCategory)
class OrgCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "get_thumbnail_preview", "created_at")
    list_filter = ("organization",)
    search_fields = ("name", "organization__name")
    autocomplete_fields = ("organization",)

    @admin.display(description="Thumbnail Preview")
    def get_thumbnail_preview(self, obj):
        if obj.thumbnail:
            return format_html(
                '<img src="{}" style="width: 50px; height: 50px; object-fit: cover;" />',
                obj.thumbnail.url
            )
        return "No Image"


@admin.register(OrgLevel)
class OrgLevelAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "order", "created_at")
    list_filter = ("organization",)
    search_fields = ("name", "organization__name")
    autocomplete_fields = ("organization",)
    ordering = ("organization", "order")