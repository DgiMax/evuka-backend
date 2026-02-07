from django.contrib import admin
from django import forms
from django.db import models
from django.utils.html import format_html
from django.utils import timezone
from .models import (
    Course, Module, Lesson, Enrollment, LessonProgress, Certificate,
    GlobalLevel, GlobalCategory, GlobalSubCategory,
    Quiz, Question, Option, QuizAttempt, Answer,
    CourseAssignment, AssignmentSubmission, CourseRating,
    CourseQuestion, CourseReply, CourseNote,
    LessonResource
)


class OptionInline(admin.TabularInline):
    model = Option
    extra = 1
    fields = ("text", "is_correct")
    max_num = 6


class QuestionInline(admin.StackedInline):
    model = Question
    extra = 1
    fields = (("text", "question_type"), ("score_weight", "order"), "instructor_hint")
    show_change_link = True


class QuizInline(admin.TabularInline):
    model = Quiz
    extra = 0
    fields = ("title", "order", "max_score", "max_attempts", "time_limit_minutes")
    show_change_link = True


class LessonResourceInline(admin.TabularInline):
    model = LessonResource
    extra = 1
    fields = ("title", "resource_type", "order", "file", "external_url", "course_book", "reading_instructions")
    autocomplete_fields = ("course_book",)


class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 0
    fields = ("title", "order", "video_file", "estimated_duration_minutes", "is_preview")
    show_change_link = True


class AssignmentInline(admin.TabularInline):
    model = CourseAssignment
    extra = 0
    fields = ("title", "order", "due_date", "max_score")
    show_change_link = True


class ModuleInline(admin.TabularInline):
    model = Module
    extra = 0
    fields = ("title", "order")
    show_change_link = True


@admin.register(GlobalCategory)
class GlobalCategoryAdmin(admin.ModelAdmin):
    list_display = ("thumbnail_tag", "name", "slug", "get_subcategory_count")
    search_fields = ("name", "description", "slug")
    prepopulated_fields = {"slug": ("name",)}

    def thumbnail_tag(self, obj):
        if obj.thumbnail:
            return format_html(
                '<img src="{}" style="width: 30px; height: 30px; border-radius: 4px; object-fit: cover;" />',
                obj.thumbnail.url)
        return "-"

    thumbnail_tag.short_description = "Icon"

    def get_subcategory_count(self, obj):
        return obj.subcategories.count()

    get_subcategory_count.short_description = "Sub-categories"


@admin.register(GlobalSubCategory)
class GlobalSubCategoryAdmin(admin.ModelAdmin):
    list_display = ("thumbnail_tag", "name", "category", "slug")
    list_filter = ("category",)
    search_fields = ("name", "category__name", "slug", "description")
    autocomplete_fields = ("category",)
    prepopulated_fields = {"slug": ("name",)}

    def thumbnail_tag(self, obj):
        if obj.thumbnail:
            return format_html(
                '<img src="{}" style="width: 30px; height: 30px; border-radius: 4px; object-fit: cover;" />',
                obj.thumbnail.url)
        return "-"


@admin.register(GlobalLevel)
class GlobalLevelAdmin(admin.ModelAdmin):
    list_display = ("order", "name", "description")
    search_fields = ("name",)
    ordering = ("order",)


class CourseAdminForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = "__all__"
        widgets = {
            "short_description": forms.Textarea(attrs={"rows": 2}),
            "long_description": forms.Textarea(attrs={"rows": 10}),
            "learning_objectives": forms.Textarea(attrs={"rows": 5}),
            "metadata": forms.Textarea(attrs={"rows": 3}),
        }


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    form = CourseAdminForm
    list_display = (
        "title", "status", "status_colored", "course_type", "organization",
        "price", "rating_avg", "num_ratings", "is_public", "created_at"
    )
    list_filter = (
        "status", "course_type", "is_public",
        "global_level", "organization", "org_category",
        ("created_at", admin.DateFieldListFilter),
    )
    list_editable = ("is_public", "status")
    search_fields = ("title", "short_description", "long_description", "slug", "creator__email", "organization__name")
    autocomplete_fields = (
        "creator", "creator_profile", "organization",
        "org_category", "org_level", "global_subcategory", "global_level", "instructors"
    )
    filter_horizontal = ("instructors",)
    readonly_fields = ("course_type", "rating_avg", "num_ratings", "created_at", "updated_at")
    save_on_top = True
    inlines = [ModuleInline]

    fieldsets = (
        ("Basic Info", {
            "fields": (("title", "status"), "slug", "short_description", "long_description", "learning_objectives")
        }),
        ("Media Assets", {
            "fields": (("thumbnail", "promo_video"),)
        }),
        ("Ownership & Teaching", {
            "fields": ("creator", "creator_profile", "organization", "instructors")
        }),
        ("Classification", {
            "fields": (("org_category", "org_level"), ("global_subcategory", "global_level"))
        }),
        ("Pricing & Market Visibility", {
            "fields": (("price", "is_public"),)
        }),
        ("Metrics & System Metadata", {
            "classes": ("collapse",),
            "fields": ("rating_avg", "num_ratings", "metadata", "created_at", "updated_at")
        }),
    )

    def status_colored(self, obj):
        colors = {
            "draft": "#777",
            "pending_review": "#f39c12",
            "published": "#27ae60",
            "archived": "#e74c3c"
        }
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            colors.get(obj.status, "#000"),
            obj.get_status_display()
        )

    status_colored.short_description = "Status Indicator"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "organization", "creator", "global_subcategory", "global_level"
        )


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ("title", "course", "order", "lesson_count")
    list_filter = ("course",)
    search_fields = ("title", "course__title")
    autocomplete_fields = ("course",)
    inlines = [LessonInline, AssignmentInline]

    def lesson_count(self, obj):
        return obj.lessons.count()

    lesson_count.short_description = "Lessons"


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ("title", "module", "organization", "order", "is_preview", "duration")
    list_filter = ("is_preview", "module__course", "organization")
    search_fields = ("title", "content", "module__title")
    autocomplete_fields = ("module", "organization")
    inlines = [LessonResourceInline, QuizInline]

    def duration(self, obj):
        return f"{obj.estimated_duration_minutes} min"


@admin.register(LessonResource)
class LessonResourceAdmin(admin.ModelAdmin):
    list_display = ("title", "lesson", "resource_type", "order")
    list_filter = ("resource_type", "lesson__module__course")
    search_fields = ("title", "lesson__title", "external_url")
    autocomplete_fields = ("lesson", "course_book")


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("user", "course", "role", "status", "progress_percent", "is_completed", "date_joined")
    list_filter = ("role", "status", "is_completed", "course")
    search_fields = ("user__username", "user__email", "course__title")
    autocomplete_fields = ("user", "course")
    readonly_fields = ("date_joined",)


@admin.register(LessonProgress)
class LessonProgressAdmin(admin.ModelAdmin):
    list_display = ("user", "lesson", "is_completed", "last_watched_timestamp", "updated_at")
    list_filter = ("is_completed", "lesson__module__course")
    search_fields = ("user__username", "lesson__title")
    autocomplete_fields = ("user", "lesson")
    readonly_fields = ("completed_at", "created_at", "updated_at")


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display = ("certificate_uid", "user", "course", "issue_date")
    list_filter = ("course", "issue_date")
    search_fields = ("certificate_uid", "user__username", "course__title")
    readonly_fields = ("certificate_uid", "issue_date")
    autocomplete_fields = ("user", "course")


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ("title", "lesson", "max_score", "max_attempts", "time_limit_minutes")
    list_filter = ("lesson__module__course",)
    search_fields = ("title", "lesson__title")
    autocomplete_fields = ("lesson",)
    inlines = [QuestionInline]


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("text", "quiz", "question_type", "score_weight")
    list_filter = ("question_type", "quiz__lesson__module__course")
    search_fields = ("text", "quiz__title")
    autocomplete_fields = ("quiz",)
    inlines = [OptionInline]


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = ("user", "quiz", "score", "max_score", "attempt_number", "is_completed", "requires_review")
    list_filter = ("is_completed", "requires_review", "quiz")
    search_fields = ("user__username", "quiz__title")
    autocomplete_fields = ("user", "quiz")
    readonly_fields = ("started_at", "completed_at", "attempt_number")


@admin.register(CourseAssignment)
class CourseAssignmentAdmin(admin.ModelAdmin):
    list_display = ("title", "module", "due_date", "max_score")
    list_filter = ("module__course",)
    search_fields = ("title", "module__title")
    autocomplete_fields = ("module",)


@admin.register(AssignmentSubmission)
class AssignmentSubmissionAdmin(admin.ModelAdmin):
    list_display = ("user", "assignment", "submission_status", "grade", "graded_by", "submitted_at")
    list_filter = ("submission_status", "assignment__module__course", ("submitted_at", admin.DateFieldListFilter))
    search_fields = ("user__username", "assignment__title")
    autocomplete_fields = ("assignment", "user", "graded_by")
    readonly_fields = ("submitted_at", "graded_at")

    fieldsets = (
        ("Submission Data", {"fields": ("assignment", "user", "file", "text_submission", "submitted_at")}),
        ("Grading & Feedback", {"fields": ("submission_status", "grade", "feedback", "graded_by", "graded_at")}),
    )


@admin.register(CourseRating)
class CourseRatingAdmin(admin.ModelAdmin):
    list_display = ("course", "user", "rating", "created_at")
    list_filter = ("rating", "course")
    search_fields = ("course__title", "user__username", "review")
    autocomplete_fields = ("course", "user")


@admin.register(CourseQuestion)
class CourseQuestionAdmin(admin.ModelAdmin):
    list_display = ("title", "course", "user", "created_at")
    list_filter = ("course", ("created_at", admin.DateFieldListFilter))
    search_fields = ("title", "content", "user__username")
    autocomplete_fields = ("course", "user")


@admin.register(CourseReply)
class CourseReplyAdmin(admin.ModelAdmin):
    list_display = ("user", "question", "is_instructor", "created_at")
    list_filter = ("is_instructor", "question__course")
    search_fields = ("content", "user__username")
    autocomplete_fields = ("question", "user")


@admin.register(CourseNote)
class CourseNoteAdmin(admin.ModelAdmin):
    list_display = ("user", "course", "updated_at")
    list_filter = ("course",)
    search_fields = ("user__username", "content")
    autocomplete_fields = ("user", "course")