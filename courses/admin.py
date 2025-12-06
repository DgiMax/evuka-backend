import uuid
from django.contrib import admin
from django import forms
from django.db import models
from .models import (
    Course, Module, Lesson, Enrollment, LessonProgress, Certificate,
    GlobalLevel, GlobalCategory, GlobalSubCategory,
    Quiz, Question, Option, QuizAttempt, Answer,
    CourseAssignment, AssignmentSubmission, CourseRating,
    CourseQuestion, CourseReply, CourseNote,
)


class OptionInline(admin.TabularInline):
    model = Option
    extra = 1
    fields = ("text", "is_correct")
    max_num = 6


class QuestionInline(admin.StackedInline):
    model = Question
    extra = 1
    fields = (
        ("text", "question_type"),
        ("score_weight", "order"),
        "instructor_hint",
    )
    inlines = [OptionInline]


class QuizInline(admin.TabularInline):
    model = Quiz
    extra = 1
    fields = ("title", "order", "max_score", "time_limit_minutes", "max_attempts")
    show_change_link = True


class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 1
    fields = (
        "title", "order", "video_file",
        "estimated_duration_minutes", "is_preview"
    )
    show_change_link = True


class AssignmentInline(admin.TabularInline):
    model = CourseAssignment
    extra = 1
    fields = ("title", "order", "due_date", "max_score")
    show_change_link = True


class ModuleInline(admin.TabularInline):
    model = Module
    extra = 1
    fields = ("title", "order")
    show_change_link = True


class GlobalSubCategoryInline(admin.TabularInline):
    model = GlobalSubCategory
    extra = 1
    fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(GlobalCategory)
class GlobalCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "get_subcategory_count")
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [GlobalSubCategoryInline]

    @admin.display(description="Subcategories")
    def get_subcategory_count(self, obj):
        return obj.subcategories.count()


@admin.register(GlobalSubCategory)
class GlobalSubCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "slug")
    list_filter = ("category",)
    search_fields = ("name", "category__name")
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ("category",)


@admin.register(GlobalLevel)
class GlobalLevelAdmin(admin.ModelAdmin):
    list_display = ("name", "order", "description")
    ordering = ("order",)
    search_fields = ("name",)


class CourseAdminForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = "__all__"
        widgets = {
            "long_description": forms.Textarea(attrs={"rows": 15}),
            "learning_objectives": forms.Textarea(attrs={"rows": 7}),
            "metadata": forms.Textarea(attrs={"rows": 5}),
        }


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    form = CourseAdminForm
    list_display = (
        "title", "course_type", "status", "organization",
        "global_subcategory", "global_level", "price",
        "get_average_rating", "num_ratings", "created_at"
    )
    list_filter = (
        "course_type", "status",
        "organization", "global_subcategory", "global_level"
    )
    search_fields = ("title", "short_description", "long_description", "slug")
    prepopulated_fields = {"slug": ("title",)}
    autocomplete_fields = (
        "creator", "creator_profile", "organization",
        "org_category", "org_level",
        "global_subcategory", "global_level", "instructors"
    )
    filter_horizontal = ("instructors",)
    inlines = [ModuleInline]
    ordering = ("-created_at",)
    readonly_fields = ("rating_avg", "num_ratings", "course_type", "created_at", "updated_at", "metadata")

    fieldsets = (
        ("Basic Info", {
            "fields": ("title", "slug", "short_description", "long_description",
                       "learning_objectives", "thumbnail", "promo_video")
        }),
        ("Classification", {
            "fields": ("course_type", "status", "organization",
                       "org_category", "org_level",
                       "global_subcategory", "global_level")
        }),
        ("Teaching & Creators", {
            "fields": ("creator", "creator_profile", "instructors")
        }),
        ("Pricing & Stats", {
            "fields": ("price", "rating_avg", "num_ratings")
        }),
        ("Visibility", {
            "fields": ("is_public",)
        }),
        ("Metadata & Dates", {
            "fields": ("metadata", "created_at", "updated_at")
        })
    )

    @admin.display(description="Avg Rating")
    def get_average_rating(self, obj):
        return f"{obj.rating_avg:.2f}" if obj.rating_avg else "–"


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ("title", "course", "order", "get_lessons_count", "get_assignments_count")
    ordering = ("course", "order")
    inlines = [LessonInline, AssignmentInline]
    search_fields = ("title", "course__title")
    autocomplete_fields = ("course",)

    @admin.display(description="# Lessons")
    def get_lessons_count(self, obj):
        return obj.lessons.count()

    @admin.display(description="# Assignments")
    def get_assignments_count(self, obj):
        return obj.assignments.count()


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ("title", "module", "organization", "order", "video_file", "is_preview", "get_quiz_count")
    search_fields = ("title", "content")
    list_filter = ("organization", "module__course__title")
    autocomplete_fields = ("module", "organization")
    inlines = [QuizInline]

    @admin.display(description="# Quizzes")
    def get_quiz_count(self, obj):
        return obj.quizzes.count()


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("user", "course", "role", "status", "date_joined")
    list_filter = ("status", "role", "course__title")
    search_fields = ("user__email", "user__username", "course__title")
    autocomplete_fields = ("user", "course")


@admin.register(LessonProgress)
class LessonProgressAdmin(admin.ModelAdmin):
    list_display = ("user", "lesson", "is_completed", "completed_at", "last_watched_timestamp")
    list_filter = ("is_completed", "lesson__module__course")
    search_fields = ("user__username", "lesson__title")
    autocomplete_fields = ("user", "lesson")
    readonly_fields = ("completed_at", "last_watched_timestamp")


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display = ("user", "course", "issue_date", "certificate_uid")
    list_filter = ("course", "issue_date")
    search_fields = ("user__username", "course__title", "certificate_uid")
    autocomplete_fields = ("user", "course")
    readonly_fields = ("certificate_uid", "issue_date")


@admin.register(CourseRating)
class CourseRatingAdmin(admin.ModelAdmin):
    list_display = ("user", "course", "rating", "created_at")
    list_filter = ("rating", "course")
    search_fields = ("user__username", "review", "course__title")
    autocomplete_fields = ("user", "course")
    readonly_fields = ("created_at",)


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ("title", "lesson", "max_score", "max_attempts", "order")
    list_filter = ("lesson__module__course",)
    search_fields = ("title", "lesson__title")
    autocomplete_fields = ("lesson",)
    inlines = [QuestionInline]


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("text", "quiz", "question_type", "score_weight", "order")
    list_filter = ("question_type", "quiz__lesson__module__course")
    search_fields = ("text", "quiz__title")
    autocomplete_fields = ("quiz",)
    inlines = [OptionInline]


@admin.register(Option)
class OptionAdmin(admin.ModelAdmin):
    list_display = ("text", "question", "is_correct")
    list_filter = ("is_correct", "question__quiz")
    search_fields = ("text", "question__text")
    autocomplete_fields = ("question",)
    list_select_related = ("question",)


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = (
        "user", "quiz", "attempt_number", "score", "max_score",
        "is_completed", "requires_review", "started_at"
    )
    list_filter = ("is_completed", "requires_review", "quiz__lesson__module__course")
    search_fields = ("user__username", "quiz__title")
    autocomplete_fields = ("user", "quiz")
    readonly_fields = ("started_at", "completed_at", "max_score", "attempt_number")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('quiz')


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ("attempt", "question", "is_correct", "score_earned")
    list_filter = ("is_correct", "question__quiz")
    search_fields = ("attempt__user__username", "question__text", "user_answer_text")
    autocomplete_fields = ("attempt", "question", "selected_option")
    readonly_fields = ("score_earned",)


@admin.register(CourseAssignment)
class CourseAssignmentAdmin(admin.ModelAdmin):
    list_display = ("title", "module", "due_date", "max_score", "get_submission_count")
    list_filter = ("module__course",)
    search_fields = ("title", "module__title")
    autocomplete_fields = ("module",)

    @admin.display(description="# Submissions")
    def get_submission_count(self, obj):
        return obj.submissions.count()


@admin.register(AssignmentSubmission)
class AssignmentSubmissionAdmin(admin.ModelAdmin):
    list_display = (
        "user", "assignment", "submission_status", "grade",
        "submitted_at", "graded_by", "graded_at"
    )
    list_filter = ("submission_status", "assignment__module__course")
    search_fields = ("user__username", "assignment__title")
    autocomplete_fields = ("user", "assignment", "graded_by")
    readonly_fields = ("submitted_at", "graded_at")
    fieldsets = (
        ("Submission Info", {
            "fields": ("assignment", "user", "file", "text_submission", "submitted_at")
        }),
        ("Grading", {
            "fields": ("submission_status", "grade", "feedback", "graded_by", "graded_at")
        }),
    )


@admin.register(CourseQuestion)
class CourseQuestionAdmin(admin.ModelAdmin):
    list_display = ("title", "course", "user", "created_at", "get_reply_count")
    list_filter = ("course",)
    search_fields = ("title", "content", "user__username")
    autocomplete_fields = ("course", "user")
    readonly_fields = ("created_at", "updated_at")

    @admin.display(description="# Replies")
    def get_reply_count(self, obj):
        return obj.replies.count()


@admin.register(CourseReply)
class CourseReplyAdmin(admin.ModelAdmin):
    list_display = ("user", "question", "is_instructor", "created_at")
    list_filter = ("is_instructor", "question__course")
    search_fields = ("content", "user__username")
    autocomplete_fields = ("question", "user")
    readonly_fields = ("created_at",)


@admin.register(CourseNote)
class CourseNoteAdmin(admin.ModelAdmin):
    list_display = ("user", "course", "updated_at")
    list_filter = ("course",)
    search_fields = ("user__username", "content")
    autocomplete_fields = ("user", "course")
    readonly_fields = ("created_at", "updated_at")
    formfield_overrides = {
        models.TextField: {'widget': forms.Textarea(attrs={'rows': 10})},
    }