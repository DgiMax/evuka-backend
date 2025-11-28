import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models import Count, Q

from live.models import LiveClass
from organizations.models import Organization, OrgLevel, OrgCategory
from users.models import CreatorProfile


class GlobalCategory(models.Model):
    """General/global categories for independent courses (Marketplace taxonomy)."""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    slug = models.SlugField(unique=True)

    thumbnail = models.ImageField(
        upload_to='category_thumbnails/',
        blank=True,
        null=True,
        help_text="Image/icon representing the global category."
    )

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Global Categories"

    def __str__(self):
        return self.name


class GlobalSubCategory(models.Model):
    """
    A subcategory that belongs to a single GlobalCategory.
    e.g., "Web Development" (SubCategory) under "Technology" (Category).
    """
    category = models.ForeignKey(
        GlobalCategory,
        on_delete=models.CASCADE,
        related_name="subcategories",
        help_text="The main category this subcategory belongs to."
    )
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True)

    thumbnail = models.ImageField(
        upload_to='subcategory_thumbnails/',
        blank=True,
        null=True,
        help_text="Image/icon representing the global subcategory."
    )

    class Meta:
        # A subcategory name must be unique within its parent
        unique_together = ('category', 'name')
        ordering = ['category', 'name']
        verbose_name_plural = "Global Subcategories"

    def __str__(self):
        # Provides a nice, readable name like: "Technology > Web Development"
        return f"{self.category.name} > {self.name}"

    def save(self, *args, **kwargs):
        if not self.slug:
            # Auto-generate a unique slug, e.g., "web-development"
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class GlobalLevel(models.Model):
    """General/global levels (Beginner, Intermediate, Advanced)."""
    name = models.CharField(max_length=100, unique=True)
    order = models.PositiveIntegerField(default=0, help_text="For sorting levels")
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["order"]
        verbose_name_plural = "Global Levels"

    def __str__(self):
        return self.name


class CourseQuerySet(models.QuerySet):
    """Custom QuerySet to annotate popularity and filter published courses."""
    def published(self):
        return self.filter(status='published')

    def annotate_popularity(self):
        """Annotates the queryset with the count of active enrollments."""
        return self.annotate(
            active_enrollment_count=Count(
                'enrollments',
                filter=Q(enrollments__status='active'),
                distinct=True
            )
        )


class Course(models.Model):
    COURSE_TYPE_CHOICES = [
        ("organization", "Organization"),
        ("independent", "Independent"),
    ]

    COURSE_STATUS_CHOICES = [
        ("draft", "Draft"),
        ("pending_review", "Pending Review"),
        ("published", "Published"),
        ("archived", "ArchIVED"),
    ]

    title = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)

    short_description = models.CharField(max_length=500, blank=True, help_text="Brief course summary")
    long_description = models.TextField(blank=True, help_text="Full course description (Markdown supported)")

    learning_objectives = models.JSONField(default=list, blank=True, help_text="List of course objectives")

    thumbnail = models.ImageField(upload_to='course_thumbnails/', blank=True, null=True)
    promo_video = models.FileField(upload_to='course_promo_videos/', blank=True, null=True)

    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_courses"
    )
    creator_profile = models.ForeignKey(
        CreatorProfile,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="courses"
    )
    organization = models.ForeignKey(
        Organization,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="courses"
    )

    org_category = models.ForeignKey(
        OrgCategory,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="courses"
    )
    org_level = models.ForeignKey(
        OrgLevel,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="courses"
    )

    global_subcategory = models.ForeignKey(
        GlobalSubCategory,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="courses",
        help_text="The specific global subcategory for this course."
    )

    global_level = models.ForeignKey(
        GlobalLevel,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="courses"
    )

    instructors = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="teaching_courses"
    )

    course_type = models.CharField(
        max_length=20, choices=COURSE_TYPE_CHOICES, default="independent"
    )

    status = models.CharField(
        max_length=20,
        choices=COURSE_STATUS_CHOICES,
        default="draft",
        help_text="Workflow status: Draft, Pending Review, Published, or Archived"
    )

    price = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    is_published = models.BooleanField(default=False)
    is_public = models.BooleanField(
        default=False,
        help_text="If True, course is visible outside the organization's portal (in the main marketplace). Only relevant for organization courses."
    )
    metadata = models.JSONField(default=dict, blank=True)
    rating_avg = models.FloatField(default=0)
    num_ratings = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    objects = CourseQuerySet.as_manager()

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return f"{self.title} ({self.status})"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)

        # Infer course type based on organization
        self.course_type = "organization" if self.organization else "independent"

        if self.course_type == "organization":
            if not self.org_category or not self.org_level:
                raise ValueError("Organization courses must have OrgCategory and OrgLevel.")
            if self.is_published and (not self.global_subcategory or not self.global_level):
                raise ValueError("Published organization courses must have GlobalSubCategory and GlobalLevel.")
        elif self.course_type == "independent":
            if not self.global_subcategory or not self.global_level:
                raise ValueError("Independent courses must have GlobalSubCategory and GlobalLevel.")
            self.org_category = None
            self.org_level = None

        # Sync is_published with status
        self.is_published = self.status == "published"

        super().save(*args, **kwargs)

    def publish(self):
        self.status = "published"
        self.is_published = True
        self.save()

    def archive(self):
        self.status = "archived"
        self.is_published = False
        self.save()


class CourseNote(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="course_notes")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="student_notes")

    content = models.TextField(blank=True, default="<p></p>")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'course')


class CourseQuestion(models.Model):
    course = models.ForeignKey('Course', on_delete=models.CASCADE, related_name='discussions')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='course_questions')

    title = models.CharField(max_length=255)
    content = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class CourseReply(models.Model):
    question = models.ForeignKey(CourseQuestion, on_delete=models.CASCADE, related_name='replies')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    content = models.TextField()
    is_instructor = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']


class CourseRating(models.Model):
    """User ratings and reviews for courses."""
    course = models.ForeignKey(Course, related_name="ratings", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    rating = models.PositiveIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    review = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("course", "user")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} rated {self.course} ({self.rating}/5)"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.course.num_ratings = self.course.ratings.count()
        self.course.rating_avg = self.course.ratings.aggregate(models.Avg("rating"))["rating__avg"] or 0
        self.course.save(update_fields=["num_ratings", "rating_avg"])


class Module(models.Model):
    course = models.ForeignKey(Course, related_name="modules", on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"{self.title} ({self.course.title})"


class Lesson(models.Model):
    module = models.ForeignKey(Module, related_name="lessons", on_delete=models.CASCADE, null=True, blank=True)
    organization = models.ForeignKey(Organization, related_name="lessons", on_delete=models.CASCADE, null=True,
                                     blank=True)
    title = models.CharField(max_length=255)
    content = models.TextField(help_text="Markdown supported")
    resources = models.JSONField(default=dict, blank=True)
    video_file = models.FileField(upload_to='lesson_videos/', blank=True, null=True)
    order = models.PositiveIntegerField(default=0)
    estimated_duration_minutes = models.PositiveIntegerField(default=0, help_text="Estimated duration in minutes")
    is_preview = models.BooleanField(default=False)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.title


class Enrollment(models.Model):
    ROLE_CHOICES = [
        ("student", "Student"),
        ("teacher", "Teacher"),
        ("ta", "Teaching Assistant"),
    ]
    STATUS_CHOICES = [
        ("active", "Active"),
        ("dropped", "Dropped"),
        ("Suspended", "Suspended"),
        ("completed", "Completed"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="enrollments", on_delete=models.CASCADE)
    course = models.ForeignKey(Course, related_name="enrollments", on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="student")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    date_joined = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ("user", "course")

    def __str__(self):
        return f"{self.user} as {self.role} in {self.course}"


class LessonProgress(models.Model):
    """Tracks a user's progress and completion of a specific lesson."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="lesson_progress", on_delete=models.CASCADE)
    lesson = models.ForeignKey(Lesson, related_name="progress_records", on_delete=models.CASCADE)

    last_watched_timestamp = models.PositiveIntegerField(default=0)

    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("user", "lesson")

    def __str__(self):
        status = "Completed" if self.is_completed else "In Progress"
        return f"{self.user.username} - {self.lesson.title} ({status})"

    def mark_as_completed(self):
        """A helper method to mark the lesson as complete."""
        if not self.is_completed:
            self.is_completed = True
            self.completed_at = timezone.now()
            self.save()


class Certificate(models.Model):
    """Represents a certificate awarded to a user for completing a course."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="certificates", on_delete=models.CASCADE)
    course = models.ForeignKey(Course, related_name="certificates", on_delete=models.CASCADE)
    issue_date = models.DateField(auto_now_add=True)
    certificate_uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    class Meta:
        # A user can only get one certificate per course
        unique_together = ("user", "course")

    def __str__(self):
        return f"Certificate for {self.user.username} in {self.course.title}"


class Quiz(models.Model):
    """Represents a quiz or assessment tied to a specific lesson."""
    lesson = models.ForeignKey(
        'Lesson',
        related_name='quizzes',
        on_delete=models.CASCADE,
        help_text="The lesson this quiz is associated with."
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    max_score = models.PositiveIntegerField(default=10, help_text="Total possible score for this quiz.")
    time_limit_minutes = models.PositiveIntegerField(null=True, blank=True, help_text="Optional time limit in minutes.")
    max_attempts = models.PositiveIntegerField(default=3)

    class Meta:
        ordering = ['lesson', 'order']
        verbose_name_plural = "Quizzes"

    def __str__(self):
        return f"Quiz: {self.title} in {self.lesson.title}"


class Question(models.Model):
    """Represents a question within a Quiz."""
    QUESTION_TYPE_CHOICES = [
        ('mcq', 'Multiple Choice'),
        ('text', 'Text Answer'),
    ]

    quiz = models.ForeignKey(Quiz, related_name='questions', on_delete=models.CASCADE)
    text = models.TextField(help_text="The text of the question.")
    question_type = models.CharField(max_length=10, choices=QUESTION_TYPE_CHOICES, default='mcq')
    order = models.PositiveIntegerField(default=0)
    score_weight = models.PositiveIntegerField(default=1)
    instructor_hint = models.TextField(blank=True, null=True, help_text="Expected answer/notes for grader.")

    class Meta:
        ordering = ['quiz', 'order']

class Option(models.Model):
    """Represents a choice/option for a Multiple Choice Question (MCQ)."""
    question = models.ForeignKey(Question, related_name='options', on_delete=models.CASCADE)
    text = models.CharField(max_length=500)
    is_correct = models.BooleanField(default=False)

    class Meta:
        unique_together = ('question', 'text')

class QuizAttempt(models.Model):
    """Records a specific user's attempt at a Quiz."""
    quiz = models.ForeignKey(Quiz, related_name='attempts', on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='quiz_attempts', on_delete=models.CASCADE)
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    max_score = models.PositiveIntegerField(default=10)
    attempt_number = models.PositiveIntegerField(default=1)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    is_completed = models.BooleanField(default=False)
    requires_review = models.BooleanField(default=False, help_text="True if a text answer needs manual grading.")

    class Meta:
        unique_together = ('quiz', 'user', 'attempt_number')
        ordering = ['quiz', 'user', '-attempt_number']

class Answer(models.Model):
    """Records a specific user's answer for a Question within a QuizAttempt."""
    attempt = models.ForeignKey(QuizAttempt, related_name='answers', on_delete=models.CASCADE)
    question = models.ForeignKey(Question, related_name='answers', on_delete=models.CASCADE)
    selected_option = models.ForeignKey(Option, on_delete=models.SET_NULL, null=True, blank=True)
    user_answer_text = models.TextField(blank=True)
    is_correct = models.BooleanField(default=False)
    score_earned = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta:
        unique_together = ('attempt', 'question')


class CourseAssignment(models.Model):
    """Assignments/Projects tied to a Module."""
    module = models.ForeignKey('Module', related_name="assignments", on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, help_text="Full instructions for the assignment.")
    due_date = models.DateTimeField(null=True, blank=True)
    max_score = models.PositiveIntegerField(default=100)

    def __str__(self):
        return f"Assignment: {self.title} in Module: {self.module.title}"


class AssignmentSubmission(models.Model):
    """User submission for a CourseAssignment."""
    SUBMISSION_STATUS_CHOICES = [
        ("pending", "Pending Review"),
        ("graded", "Graded"),
        ("resubmit", "Request Resubmission"),
        ("expired", "Expired/Late"),
    ]

    assignment = models.ForeignKey(CourseAssignment, related_name="submissions", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="assignment_submissions", on_delete=models.CASCADE)
    file = models.FileField(upload_to='assignment_submissions/', null=True, blank=True)
    text_submission = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    submission_status = models.CharField(
        max_length=20,
        choices=SUBMISSION_STATUS_CHOICES,
        default="pending",
        help_text="The grading status of the submission."
    )
    graded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="graded_submissions",
        help_text="The user (tutor/admin) who graded this submission."
    )
    graded_at = models.DateTimeField(null=True, blank=True)
    grade = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    feedback = models.TextField(blank=True)

    class Meta:
        unique_together = ("assignment", "user")

    def __str__(self):
        return f"Submission by {self.user} for {self.assignment.title}"