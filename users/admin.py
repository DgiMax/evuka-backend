from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html

from .models import (
    CreatorProfile,
    StudentProfile,
    Subject,
    TutorPayoutMethod,
    NewsletterSubscriber,
)

User = get_user_model()


class StudentProfileInline(admin.StackedInline):
    """
    Makes the StudentProfile editable right from the User page.
    """
    model = StudentProfile
    can_delete = False
    verbose_name_plural = 'Student Profile'
    fields = ('avatar', 'bio', 'preferences')


class CreatorProfileInline(admin.StackedInline):
    """
    Makes the CreatorProfile editable right from the User page.
    """
    model = CreatorProfile
    can_delete = False
    verbose_name_plural = 'Creator Profile'
    fields = (
        'display_name', 'headline', 'bio',
        'profile_image', 'intro_video',
        'education', 'is_verified', 'subjects'
    )
    filter_horizontal = ('subjects',)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """
    A much cleaner User admin, now with profiles built-in.
    """
    list_display = (
        "username", "email",
        "is_active", "is_verified",
        "get_user_roles",
        "is_staff",
    )
    list_filter = (
        "is_active", "is_verified",
        "is_staff", "is_superuser",
        "is_student", "is_tutor",
    )
    search_fields = ("username", "email")
    ordering = ("username",)

    inlines = (StudentProfileInline, CreatorProfileInline)

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (_("Personal info"), {
            "fields": ("first_name", "last_name", "email")
        }),
        (_("Role Flags"), {
            "fields": ("is_student", "is_tutor")
        }),
        (_("Permissions"), {
            "fields": (
                "is_active", "is_verified",
                "is_staff", "is_superuser",
                "groups", "user_permissions"
            )
        }),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )

    readonly_fields = ('last_login', 'date_joined', 'is_student', 'is_tutor')

    @admin.display(description="Roles")
    def get_user_roles(self, obj):
        roles = []
        if obj.is_student:
            roles.append("Student")
        if obj.is_tutor:
            roles.append("Tutor")
        if not roles:
            return "None"
        colors = {"Student": "green", "Tutor": "blue"}
        return format_html("".join(
            f'<span style="background: {colors.get(role, "gray")}; color: white; padding: 3px 6px; border-radius: 4px; margin-right: 4px;">{role}</span>'
            for role in roles
        ))


@admin.register(CreatorProfile)
class CreatorProfileAdmin(admin.ModelAdmin):
    """
    A standalone admin for managing *only* Creator Profiles.
    """
    list_display = ("display_name", "user_email", "is_verified")
    list_filter = ("is_verified", "subjects")
    search_fields = ("display_name", "user__username", "user__email")
    autocomplete_fields = ('user',)
    filter_horizontal = ("subjects",)

    @admin.display(description="User Email")
    def user_email(self, obj):
        return obj.user.email


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    """
    A standalone admin for managing *only* Student Profiles.
    """
    list_display = ("user_email", "created_at")
    search_fields = ("user__username", "user__email")
    autocomplete_fields = ('user',)

    @admin.display(description="User Email")
    def user_email(self, obj):
        return obj.user.email


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    """
    Admin for managing subjects.
    """
    list_display = ('name', 'slug')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}


@admin.register(TutorPayoutMethod)
class TutorPayoutMethodAdmin(admin.ModelAdmin):
    list_display = ("profile", "method_type", "is_active", "display_details")
    list_filter = ("method_type", "is_active", "profile__is_verified")
    search_fields = (
        "profile__user__username", "profile__display_name", "display_details"
    )
    autocomplete_fields = ("profile",)
    readonly_fields = ("paystack_recipient_code",)


@admin.register(NewsletterSubscriber)
class NewsletterSubscriberAdmin(admin.ModelAdmin):
    list_display = ("email", "is_active", "created_at", "user")
    list_filter = ("is_active", "created_at")
    search_fields = ("email", "user__username")
    autocomplete_fields = ("user",)