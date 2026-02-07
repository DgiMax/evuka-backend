from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from .models import (
    CreatorProfile,
    StudentProfile,
    PublisherProfile,
    Subject,
    NewsletterSubscriber,
    BankingDetails
)

User = get_user_model()


class StudentProfileInline(admin.StackedInline):
    model = StudentProfile
    can_delete = False
    verbose_name_plural = 'Marketplace Student Profile'
    fields = ('avatar', 'bio', 'preferences')
    extra = 0


class CreatorProfileInline(admin.StackedInline):
    model = CreatorProfile
    can_delete = False
    verbose_name_plural = 'Tutor / Creator Profile'
    fields = (
        'display_name', 'headline', 'bio',
        'profile_image', 'intro_video',
        'education', 'is_verified', 'subjects'
    )
    filter_horizontal = ('subjects',)
    extra = 0


class PublisherProfileInline(admin.StackedInline):
    model = PublisherProfile
    can_delete = False
    verbose_name_plural = 'Publisher Profile'
    fields = ('display_name', 'headline', 'bio', 'profile_image', 'is_verified', 'website')
    extra = 0


class BankingDetailsInline(admin.TabularInline):
    model = BankingDetails
    can_delete = False
    verbose_name_plural = 'Payout Banking Details'
    readonly_fields = ('paystack_recipient_code', 'bank_name', 'display_number', 'is_verified')
    extra = 0


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        "username", "email",
        "is_active", "is_verified",
        "get_user_roles",
        "is_staff",
    )
    list_filter = (
        "is_active", "is_verified",
        "is_staff", "is_superuser",
        "is_student", "is_tutor", "is_publisher",
    )
    search_fields = ("username", "email", "first_name", "last_name")
    ordering = ("-date_joined",)

    inlines = (StudentProfileInline, CreatorProfileInline, PublisherProfileInline, BankingDetailsInline)

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (_("Personal info"), {
            "fields": ("first_name", "last_name", "email")
        }),
        (_("Role Flags"), {
            "fields": (("is_student", "is_tutor", "is_publisher"), "is_verified")
        }),
        (_("Permissions"), {
            "fields": (
                "is_active", "is_staff", "is_superuser",
                "groups", "user_permissions"
            )
        }),
        (_("System Status"), {
            "fields": ("ecosystem_email_sent", "roles_welcome_sent")
        }),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )

    readonly_fields = ('last_login', 'date_joined', 'roles_welcome_sent')

    @admin.display(description="Active Roles")
    def get_user_roles(self, obj):
        roles = []
        if obj.is_student: roles.append(("Student", "#27ae60"))
        if obj.is_tutor: roles.append(("Tutor", "#2980b9"))
        if obj.is_publisher: roles.append(("Publisher", "#8e44ad"))

        if not roles:
            return format_html('<span style="color: #999;">No Roles</span>')

        return format_html(" ".join(
            f'<span style="background: {color}; color: white; padding: 2px 8px; border-radius: 12px; font-size: 10px; font-weight: bold; margin-right: 4px; text-transform: uppercase;">{name}</span>'
            for name, color in roles
        ))

@admin.register(CreatorProfile)
class CreatorProfileAdmin(admin.ModelAdmin):
    list_display = ("display_name", "user_link", "is_verified", "subject_list")
    list_filter = ("is_verified", "subjects")
    search_fields = ("display_name", "user__username", "user__email")
    autocomplete_fields = ('user',)
    filter_horizontal = ("subjects",)

    def user_link(self, obj):
        return obj.user.email

    user_link.short_description = "User Email"

    def subject_list(self, obj):
        return ", ".join([s.name for s in obj.subjects.all()])


@admin.register(PublisherProfile)
class PublisherProfileAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'user_email', 'is_verified', 'created_at')
    list_filter = ('is_verified', 'created_at')
    search_fields = ('display_name', 'user__username', 'user__email')
    autocomplete_fields = ('user',)

    def user_email(self, obj):
        return obj.user.email


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ("user_email", "created_at")
    search_fields = ("user__username", "user__email")
    autocomplete_fields = ('user',)

    def user_email(self, obj):
        return obj.user.email


@admin.register(BankingDetails)
class BankingDetailsAdmin(admin.ModelAdmin):
    list_display = ('user', 'bank_name', 'display_number', 'is_verified')
    list_filter = ('is_verified', 'bank_name')
    search_fields = ('user__username', 'user__email', 'display_number')
    autocomplete_fields = ('user',)


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}


@admin.register(NewsletterSubscriber)
class NewsletterSubscriberAdmin(admin.ModelAdmin):
    list_display = ("email", "is_active", "created_at", "user")
    list_filter = ("is_active", "created_at")
    search_fields = ("email", "user__username")
    autocomplete_fields = ("user",)