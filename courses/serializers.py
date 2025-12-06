import json
import os
import random
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.conf import settings

from .models import Course, Module, Lesson, GlobalCategory, GlobalLevel, GlobalSubCategory, LessonProgress, Quiz, \
    Question, Option, CourseAssignment, QuizAttempt, Answer, AssignmentSubmission, Enrollment, CourseNote, \
    CourseQuestion, CourseReply
from users.models import CreatorProfile
from live.serializers import LiveClassSerializer, LiveClassMinimalSerializer
from django.db.models import Sum, Case, When


User = get_user_model()


class InstructorSummarySerializer(serializers.ModelSerializer):
    """Basic instructor info used across views."""
    instructor_name = serializers.CharField(source='user.get_full_name')

    class Meta:
        model = CreatorProfile
        fields = ("instructor_name", "bio")


class GlobalCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = GlobalCategory
        fields = ("name", "slug")


class GlobalSubCategorySerializer(serializers.ModelSerializer):
    """Serializes the subcategory and includes the parent category."""
    category = GlobalCategorySerializer(read_only=True)

    class Meta:
        model = GlobalSubCategory
        fields = ("name", "slug", "category")


class GlobalLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = GlobalLevel
        fields = ("name",)


class LessonBaseSerializer(serializers.ModelSerializer):
    """Base serializer with common lesson fields."""

    class Meta:
        model = Lesson
        fields = ("title", "is_preview", "estimated_duration_minutes", "video_file")


class LessonBriefSerializer(LessonBaseSerializer):
    """Lightweight lesson serializer for course details."""
    pass


class ModuleBaseSerializer(serializers.ModelSerializer):
    """Base serializer for module info."""

    class Meta:
        model = Module
        fields = ("title", "description")


class CourseListSerializer(serializers.ModelSerializer):
    instructor_name = serializers.CharField(source='creator_profile.user.get_full_name', read_only=True)
    category = serializers.CharField(source='global_subcategory.category.name', read_only=True)
    level = serializers.CharField(source='global_level.name', read_only=True)
    num_students = serializers.IntegerField(read_only=True)
    is_enrolled = serializers.BooleanField(read_only=True)
    status = serializers.CharField(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    progress = serializers.FloatField(read_only=True)

    class Meta:
        model = Course
        fields = (
            "slug", "title", "thumbnail", "short_description",
            "instructor_name", "is_enrolled", "rating_avg",
            "price", "num_students", "category", "level",
            "status", "status_display", "progress"
        )


class CourseNoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = CourseNote
        fields = ['id', 'content', 'updated_at']
        read_only_fields = ['id', 'updated_at']


class CourseReplySerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    user_avatar = serializers.ImageField(source='user.avatar', read_only=True)

    class Meta:
        model = CourseReply
        fields = ['id', 'user_name', 'user_avatar', 'content', 'is_instructor', 'created_at']

class CourseQuestionSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    replies = CourseReplySerializer(many=True, read_only=True)
    is_mine = serializers.BooleanField(read_only=True)

    class Meta:
        model = CourseQuestion
        fields = [
            'id', 'user_name', 'title', 'content',
            'created_at', 'replies', 'is_mine'
        ]
        read_only_fields = ['id', 'created_at', 'replies', 'is_mine']


class ModuleDetailSerializer(ModuleBaseSerializer):
    lessons = LessonBriefSerializer(many=True, read_only=True)
    lessons_count = serializers.IntegerField(source="lessons.count", read_only=True)

    class Meta(ModuleBaseSerializer.Meta):
        fields = ModuleBaseSerializer.Meta.fields + ("lessons_count", "lessons")


class CourseDetailSerializer(serializers.ModelSerializer):
    instructor = InstructorSummarySerializer(source="creator_profile", read_only=True)
    modules = ModuleDetailSerializer(many=True, read_only=True)
    category = GlobalSubCategorySerializer(source="global_subcategory", read_only=True)
    level = GlobalLevelSerializer(source="global_level", read_only=True)
    organization_name = serializers.CharField(source="organization.name", read_only=True)
    is_enrolled = serializers.BooleanField(read_only=True)
    num_students = serializers.IntegerField(read_only=True)
    status = serializers.CharField(read_only=True)
    live_classes = LiveClassSerializer(many=True, read_only=True)

    class Meta:
        model = Course
        fields = (
            "slug", "title", "short_description", "long_description",
            "learning_objectives", "thumbnail",
            "promo_video",
            "instructor", "organization_name", "category", "level",
            "price", "rating_avg", "num_students", "num_ratings",
            "is_enrolled", "modules", "status", "created_at", "updated_at",
            "live_classes",
        )

    def to_representation(self, instance):
        """Pass context to nested serializers."""
        data = super().to_representation(instance)

        if 'request' in self.context and 'live_classes' in data:
            live_classes_qs = instance.live_classes.all()
            data['live_classes'] = LiveClassSerializer(
                live_classes_qs,
                many=True,
                context=self.context
            ).data
        return data


class QuizAttemptMinimalSerializer(serializers.ModelSerializer):
    """Minimal data for a student's latest attempt used on the learning dashboard."""
    class Meta:
        model = QuizAttempt
        fields = ('score', 'max_score', 'attempt_number', 'is_completed', 'requires_review', 'completed_at')


class QuizQuestionLearningSerializer(serializers.ModelSerializer):
    options = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = ('id', 'text', 'question_type', 'score_weight', 'order', 'options')

    def get_options(self, obj):
        shuffled_options = list(obj.options.all())
        random.shuffle(shuffled_options)

        return [{'id': opt.id, 'text': opt.text} for opt in shuffled_options]


class QuizLearningSerializer(serializers.ModelSerializer):
    questions_count = serializers.IntegerField(source='questions.count', read_only=True)
    latest_attempt = serializers.SerializerMethodField()

    class Meta:
        model = Quiz
        fields = (
            'id', 'title', 'description', 'max_score',
            'time_limit_minutes', 'max_attempts', 'questions_count', 'latest_attempt'
        )

    def get_latest_attempt(self, obj):
        """Fetches the user's latest attempt for this quiz using the request context."""
        request = self.context.get("request")

        if not request or not request.user.is_authenticated:
            return None

        user = request.user

        latest_attempt = obj.attempts.filter(user=user).order_by('-attempt_number').first()

        if latest_attempt:
            return QuizAttemptMinimalSerializer(latest_attempt).data
        return None


class ExistingAnswerSerializer(serializers.ModelSerializer):
    """
    Serializer to return saved user answers for a quiz resumption.
    Used by GET /quizzes/{attempt_id}/answers/
    """
    question_id = serializers.ReadOnlyField(source='question.id')

    class Meta:
        model = Answer
        fields = (
            'id',
            'question_id',
            'selected_option',
            'user_answer_text',
        )
        read_only_fields = fields


class AssignmentSubmissionMinimalSerializer(serializers.ModelSerializer):
    """Minimal data required for student status updates."""
    class Meta:
        model = AssignmentSubmission
        fields = (
            'submission_status',
            'submitted_at',
            'grade',
            'file',
            'feedback',
            'text_submission'
        )


class CourseAssignmentLearningSerializer(serializers.ModelSerializer):
    latest_submission = serializers.SerializerMethodField()

    class Meta:
        model = CourseAssignment
        fields = ('id', 'title', 'description', 'due_date', 'max_score', 'latest_submission')

    def get_latest_submission(self, obj):
        """Fetches the user's latest submission for this assignment."""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None

        user = request.user
        latest_submission = obj.submissions.filter(user=user).order_by('-submitted_at').first()

        if latest_submission:
            return AssignmentSubmissionMinimalSerializer(latest_submission).data
        return None


class AssignmentSubmissionCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating or updating an AssignmentSubmission via FormData.
    Requires at least one of 'file' or 'text_submission'.
    """

    class Meta:
        model = AssignmentSubmission
        fields = ('file', 'text_submission')

    def validate(self, data):
        """Ensure at least a file or text is submitted."""
        if not data.get('file') and not data.get('text_submission'):
            raise serializers.ValidationError("You must submit either a file or text content.")

        if 'text_submission' in data and data['text_submission'] == '':
            data['text_submission'] = None

        return data


class LessonLearningSerializer(serializers.ModelSerializer):
    is_completed = serializers.SerializerMethodField()
    last_watched_timestamp = serializers.SerializerMethodField()
    quizzes = QuizLearningSerializer(many=True, read_only=True)

    class Meta:
        model = Lesson
        fields = (
            "id", "title", "content", "video_file", "resources",
            "estimated_duration_minutes", "is_completed", "last_watched_timestamp",
            "quizzes"
        )

    def get_user(self):
        if "request" not in self.context:
            return None
        return self.context["request"].user

    def _get_progress(self, obj):
        user = self.get_user()
        if not user:
            return None
        return LessonProgress.objects.filter(user=user, lesson=obj).first()

    def get_is_completed(self, obj):
        progress = self._get_progress(obj)
        return progress.is_completed if progress else False

    def get_last_watched_timestamp(self, obj):
        progress = self._get_progress(obj)
        return progress.last_watched_timestamp if progress else 0


class ModuleLearningSerializer(ModuleBaseSerializer):
    lessons = LessonLearningSerializer(many=True, read_only=True)
    assignments = CourseAssignmentLearningSerializer(many=True, read_only=True)

    class Meta(ModuleBaseSerializer.Meta):
        fields = ModuleBaseSerializer.Meta.fields + ("lessons", "assignments")


class CourseLearningSerializer(serializers.ModelSerializer):
    """
    Serializer for the student learning view (/courses/{slug}/learn/).
    Includes curriculum, live sessions, overview content, and necessary user context.
    """
    modules = ModuleLearningSerializer(many=True, read_only=True)
    live_classes = LiveClassSerializer(many=True, read_only=True)
    creator_name = serializers.CharField(
        source='creator_profile.user.get_full_name', read_only=True
    )
    is_enrolled = serializers.BooleanField(read_only=True)

    class Meta:
        model = Course
        fields = (
            "title",
            "slug",
            "long_description",
            "learning_objectives",
            "creator_name",
            "is_enrolled",
            "modules",
            "live_classes"
        )

    def to_representation(self, instance):
        """Pass context (request) to nested serializers, especially for generating Jitsi JWTs
        and fetching user-specific quiz attempt data."""
        data = super().to_representation(instance)

        if 'request' in self.context and 'live_classes' in data:
            live_classes_qs = instance.live_classes.all()
            data['live_classes'] = LiveClassSerializer(
                live_classes_qs,
                many=True,
                context=self.context
            ).data

        if 'request' in self.context and 'modules' in data:
            modules_qs = instance.modules.all()
            data['modules'] = ModuleLearningSerializer(
                modules_qs,
                many=True,
                context=self.context
            ).data

        return data


class OptionCreateUpdateSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = Option
        fields = ('id', 'text', 'is_correct')


class QuestionCreateUpdateSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    options = OptionCreateUpdateSerializer(many=True, required=False)

    class Meta:
        model = Question
        fields = ('id', 'text', 'question_type', 'score_weight', 'order', 'instructor_hint', 'options')


class QuizCreateUpdateSerializer(serializers.ModelSerializer):
    """
    Used for the Full Quiz Editor in Tutor Dashboard.
    Handles nested creation/update of Questions -> Options.
    """
    id = serializers.IntegerField(required=False)
    questions = QuestionCreateUpdateSerializer(many=True, required=False)

    class Meta:
        model = Quiz
        fields = ('id', 'title', 'description', 'order', 'max_score', 'time_limit_minutes', 'max_attempts', 'questions')

    def create(self, validated_data):
        """
        Handles creating a Quiz with nested Questions and Options.
        """
        questions_data = validated_data.pop('questions', [])
        quiz = Quiz.objects.create(**validated_data)

        for q_data in questions_data:
            options_data = q_data.pop('options', [])
            question = Question.objects.create(quiz=quiz, **q_data)

            for o_data in options_data:
                Option.objects.create(question=question, **o_data)

        return quiz

    def update(self, instance, validated_data):
        questions_data = validated_data.pop('questions', [])

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if questions_data is not None:
            keep_question_ids = []

            for q_data in questions_data:
                options_data = q_data.pop('options', [])
                q_id = q_data.get('id')

                if q_id:
                    question = Question.objects.get(id=q_id, quiz=instance)
                    for q_attr, q_val in q_data.items():
                        setattr(question, q_attr, q_val)
                    question.save()
                else:
                    question = Question.objects.create(quiz=instance, **q_data)

                keep_question_ids.append(question.id)

                keep_option_ids = []
                for o_data in options_data:
                    o_id = o_data.get('id')
                    if o_id:
                        option = Option.objects.get(id=o_id, question=question)
                        for o_attr, o_val in o_data.items():
                            setattr(option, o_attr, o_val)
                        option.save()
                    else:
                        option = Option.objects.create(question=question, **o_data)
                    keep_option_ids.append(option.id)

                question.options.exclude(id__in=keep_option_ids).delete()

            instance.questions.exclude(id__in=keep_question_ids).delete()

        return instance


class CourseAssignmentCreateUpdateSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = CourseAssignment
        fields = ('id', 'title', 'description', 'due_date', 'max_score')


class LessonCreateUpdateSerializer(serializers.ModelSerializer):
    quizzes = QuizCreateUpdateSerializer(many=True, required=False)

    class Meta:
        model = Lesson
        fields = ("title", "content", "video_file", "quizzes")


class ModuleCreateUpdateSerializer(serializers.ModelSerializer):
    lessons = LessonCreateUpdateSerializer(many=True)
    assignments = CourseAssignmentCreateUpdateSerializer(many=True, required=False)

    class Meta:
        model = Module
        fields = ("title", "description", "lessons", "assignments")


class LessonTutorDetailSerializer(serializers.ModelSerializer):
    """ Serializer to READ lesson data for the edit form """
    video_file = serializers.SerializerMethodField()
    quizzes = QuizCreateUpdateSerializer(many=True, read_only=True)

    class Meta:
        model = Lesson
        fields = ('id', 'title', 'content', 'video_file', 'quizzes')

    def get_video_file(self, obj):
        if obj.video_file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.video_file.url)
            return obj.video_file.url
        return None


class ModuleTutorDetailSerializer(serializers.ModelSerializer):
    """ Serializer to READ module data for the edit form """
    lessons = LessonTutorDetailSerializer(many=True, read_only=True)
    assignments = CourseAssignmentCreateUpdateSerializer(many=True, read_only=True)

    class Meta:
        model = Module
        fields = ('id', 'title', 'description', 'lessons', 'assignments')


class TutorCourseDetailSerializer(serializers.ModelSerializer):
    global_category = serializers.SerializerMethodField()
    modules = ModuleTutorDetailSerializer(many=True, read_only=True)
    thumbnail = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = (
            "id", "title", "short_description", "long_description",
            "learning_objectives",
            "global_subcategory",
            "global_level",
            "global_category",
            "org_category",
            "org_level",
            "thumbnail",
            "promo_video",
            "price", "status", "slug",
            "modules", "is_public"
        )

    def get_global_category(self, obj):
        if obj.global_subcategory:
            return obj.global_subcategory.category_id
        return None

    def get_thumbnail(self, obj):
        """ Returns the full URL for the thumbnail """
        if obj.thumbnail:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.thumbnail.url)
            return obj.thumbnail.url
        return None


class CourseCreateUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for tutors creating or updating courses with nested modules & lessons.
    """
    thumbnail = serializers.ImageField(required=False, allow_null=True)
    modules = serializers.CharField(write_only=True, required=False)
    learning_objectives = serializers.CharField(write_only=True, required=False)
    status = serializers.ChoiceField(choices=Course.COURSE_STATUS_CHOICES, default="draft")
    global_category = serializers.PrimaryKeyRelatedField(
        queryset=GlobalCategory.objects.all(), write_only=True, required=False
    )
    is_public = serializers.BooleanField(required=False)

    class Meta:
        model = Course
        fields = (
            "title", "short_description", "long_description",
            "learning_objectives",
            "global_subcategory", "global_level",
            "global_category",
            "org_category", "org_level", "thumbnail", "promo_video",
            "price", "status", "is_public", "modules",
        )

    def _parse_json_field(self, value, field_name):
        if not value:
            return []
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            raise serializers.ValidationError(f"Invalid JSON format for {field_name}.")

    def validate_modules(self, value):
        modules_data = self._parse_json_field(value, "modules")
        if not isinstance(modules_data, list):
            raise serializers.ValidationError("Modules must be a list.")
        return modules_data

    def validate_learning_objectives(self, value):
        objectives_data = self._parse_json_field(value, "learning_objectives")
        field = serializers.ListField(child=serializers.DictField(child=serializers.CharField()))
        return field.run_validation(objectives_data)

    def validate(self, data):
        """
        Conditionally validates category and level fields based on whether
        the course is an organization course (context provided by viewset)
        or an independent course.
        """
        is_org_course = self.context.get('is_organization_course', False)
        errors = {}

        global_subcategory = data.get("global_subcategory")
        global_level = data.get("global_level")

        org_category = data.get("org_category")
        org_level = data.get("org_level")

        if is_org_course:
            if not global_subcategory:
                errors['global_subcategory'] = "Global subcategory is required for organization courses."
            if not global_level:
                errors['global_level'] = "Global level is required for organization courses."

            if not org_category:
                errors['org_category'] = "Organization category is required for organization courses."
            if not org_level:
                errors['org_level'] = "Organization level is required for organization courses."

        else:
            if not global_subcategory:
                errors['global_subcategory'] = "Global subcategory is required for independent courses."
            if not global_level:
                errors['global_level'] = "Global level is required for independent courses."

            if org_category:
                errors['org_category'] = "Organization category cannot be set for independent courses."
                data.pop('org_category')
            if org_level:
                errors['org_level'] = "Organization level cannot be set for independent courses."
                data.pop('org_level')

        if errors:
            raise serializers.ValidationError(errors)

        return data

    def _create_modules(self, course, modules_data, request):
        request_files = request.FILES

        for module_data in modules_data:
            lessons_data = module_data.pop("lessons", [])
            assignments_data = module_data.pop("assignments", [])

            module_data.pop('id', None)
            module = Module.objects.create(course=course, **module_data)

            for assignment_data in assignments_data:
                assignment_data.pop('id', None)
                CourseAssignment.objects.create(module=module, **assignment_data)

            for lesson_data in lessons_data:
                quizzes_data = lesson_data.pop("quizzes", [])

                file_key_or_path = lesson_data.pop('video_file', None)
                lesson_kwargs = lesson_data.copy()
                if file_key_or_path in request_files:
                    lesson_kwargs['video_file'] = request_files[file_key_or_path]
                elif file_key_or_path and file_key_or_path.startswith(settings.MEDIA_URL):
                    relative_path = os.path.relpath(file_key_or_path, settings.MEDIA_URL)
                    lesson_kwargs['video_file'] = relative_path

                lesson_kwargs.pop('id', None)
                lesson = Lesson.objects.create(module=module, **lesson_kwargs)

                for quiz_data in quizzes_data:
                    questions_data = quiz_data.pop("questions", [])
                    quiz_data.pop('id', None)
                    quiz = Quiz.objects.create(lesson=lesson, **quiz_data)

                    for question_data in questions_data:
                        options_data = question_data.pop("options", [])
                        question_data.pop('id', None)
                        question = Question.objects.create(quiz=quiz, **question_data)

                        for option_data in options_data:
                            option_data.pop('id', None)
                            Option.objects.create(question=question, **option_data)

    def create(self, validated_data):
        modules_data = validated_data.pop("modules", [])
        objectives_data = validated_data.pop("learning_objectives", [])
        validated_data.pop("global_category", None)

        validated_data["learning_objectives"] = [
            obj["value"] for obj in objectives_data if obj.get("value")
        ]

        request = self.context.get('request')
        if not request:
            raise serializers.ValidationError("Serializer requires request in context.")

        course = Course.objects.create(**validated_data)

        self._create_modules(course, modules_data, request)

        return course

    def update(self, instance, validated_data):
        modules_data = validated_data.pop("modules", None)
        objectives_data = validated_data.pop("learning_objectives", None)
        validated_data.pop("global_category", None)

        request = self.context.get('request')
        if not request:
            raise serializers.ValidationError("Serializer requires request in context.")

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if objectives_data is not None:
            instance.learning_objectives = [obj["value"] for obj in objectives_data if obj.get("value")]

        if modules_data is not None:
            instance.modules.all().delete()
            self._create_modules(instance, modules_data, request)

        instance.save()

        return instance

    def to_representation(self, instance):
        thumbnail_url = None
        if instance.thumbnail:
            request = self.context.get('request')
            if request:
                thumbnail_url = request.build_absolute_uri(instance.thumbnail.url)
            else:
                thumbnail_url = instance.thumbnail.url
        return {
            "id": instance.id,
            "title": instance.title,
            "slug": instance.slug,
            "status": instance.status,
            "price": instance.price,
            "thumbnail_url": thumbnail_url,
            "is_public": instance.is_public
        }


class LessonPreviewSerializer(serializers.ModelSerializer):
    """Used for tutor preview mode — shows lesson content but no progress tracking."""

    class Meta:
        model = Lesson
        fields = (
            "id", "title", "content",
            "video_file",
            "resources", "estimated_duration_minutes", "is_preview"
        )


class ModulePreviewSerializer(serializers.ModelSerializer):
    lessons = LessonPreviewSerializer(many=True, read_only=True)

    class Meta:
        model = Module
        fields = ("title", "description", "lessons")


class CoursePreviewSerializer(serializers.ModelSerializer):
    modules = ModulePreviewSerializer(many=True, read_only=True)
    instructor = InstructorSummarySerializer(source="creator_profile", read_only=True)
    category = GlobalSubCategorySerializer(source="global_subcategory", read_only=True)
    level = GlobalLevelSerializer(source="global_level", read_only=True)
    organization_name = serializers.CharField(source="organization.name", read_only=True)
    live_classes = LiveClassSerializer(many=True, read_only=True)

    class Meta:
        model = Course
        fields = (
            "slug", "title", "short_description", "long_description",
            "learning_objectives", "thumbnail",
            "promo_video",
            "instructor", "organization_name", "category", "level",
            "modules", "created_at", "updated_at",
            "live_classes",
        )

    def to_representation(self, instance):
        """Pass context to nested serializers."""
        data = super().to_representation(instance)

        if 'request' in self.context and 'live_classes' in data:
            live_classes_qs = instance.live_classes.all()
            data['live_classes'] = LiveClassSerializer(
                live_classes_qs,
                many=True,
                context=self.context
            ).data
        return data


class AnswerSubmissionSerializer(serializers.Serializer):
    """
    Helper serializer used within QuizAttemptSubmissionSerializer to validate
    and parse data for a single answer.
    """
    answer_id = serializers.PrimaryKeyRelatedField(
        queryset=Answer.objects.all(),
        source='id'
    )
    selected_option_id = serializers.IntegerField(required=False, allow_null=True)
    user_answer_text = serializers.CharField(required=False, allow_blank=True)

    def validate_answer_id(self, value):
        """Ensures the submitted Answer ID belongs to the current QuizAttempt."""
        attempt = self.context.get('attempt')
        if value.attempt != attempt:
            raise serializers.ValidationError("Answer does not belong to the current attempt.")
        return value


class QuizAttemptSubmissionSerializer(serializers.Serializer):
    """
    Main serializer for processing a full quiz submission, validating all answers,
    running the grading logic, and finalizing the QuizAttempt.
    """
    answers = AnswerSubmissionSerializer(many=True)

    def save(self):
        """
        Processes the submission, performs automatic grading for MCQs,
        marks the attempt complete, and calculates the final score.
        """
        attempt = self.context.get('attempt')
        answers_data = self.validated_data['answers']
        total_score = 0
        requires_review = False

        with transaction.atomic():
            for answer_data in answers_data:
                answer = answer_data['id']
                question = answer.question
                score_earned = 0
                is_correct = False

                if question.question_type == 'mcq':
                    option_id = answer_data.get('selected_option_id')

                    if option_id:
                        try:
                            selected_option = Option.objects.get(pk=option_id, question=question)
                            answer.selected_option = selected_option

                            if selected_option.is_correct:
                                score_earned = question.score_weight
                                is_correct = True

                        except Option.DoesNotExist:
                            pass

                elif question.question_type == 'text':
                    user_text = answer_data.get('user_answer_text')
                    if user_text:
                        answer.user_answer_text = user_text
                        requires_review = True

                answer.is_correct = is_correct
                answer.score_earned = score_earned
                answer.save()
                total_score += score_earned

            attempt.score = total_score
            attempt.is_completed = True
            attempt.completed_at = timezone.now()
            attempt.requires_review = requires_review
            attempt.save()

            return total_score, requires_review


class SubmissionUserSerializer(serializers.ModelSerializer):
    """Minimal user info for displaying who submitted an assignment."""
    full_name = serializers.CharField(source='get_full_name', read_only=True)

    class Meta:
        model = User
        fields = ('id', 'full_name')


class AssignmentSubmissionManagerSerializer(serializers.ModelSerializer):
    """For tutors to view and grade a single submission."""
    user = SubmissionUserSerializer(read_only=True)
    assignment_title = serializers.CharField(source='assignment.title', read_only=True)

    class Meta:
        model = AssignmentSubmission
        fields = (
            "id", "assignment", "user", "assignment_title", "file",
            "text_submission", "submitted_at", "graded_at",
            "grade", "feedback", "submission_status", "graded_by",
        )
        read_only_fields = ("assignment", "user", "submitted_at", "graded_by")


class GradeAssignmentSerializer(serializers.ModelSerializer):
    """For tutors to submit the grade and feedback."""
    class Meta:
        model = AssignmentSubmission
        fields = ("grade", "feedback", "submission_status")

    def validate_grade(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("Grade cannot be negative.")
        return value


class QuizAttemptManagerSerializer(serializers.ModelSerializer):
    """For tutors to review quiz attempts, especially those requiring review."""
    user = SubmissionUserSerializer(read_only=True)
    quiz_title = serializers.CharField(source='quiz.title', read_only=True)
    lesson_title = serializers.CharField(source='quiz.lesson.title', read_only=True)

    class Meta:
        model = QuizAttempt
        fields = (
            "id", "quiz_title", "lesson_title", "user", "score", "max_score",
            "attempt_number", "started_at", "completed_at", "is_completed",
            "requires_review"
        )


class ModuleAtomicSerializer(serializers.ModelSerializer):
    class Meta:
        model = Module
        fields = ("id", "title", "description", "order")


class LessonCreateAtomicSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lesson
        fields = ("id", "module", "title", "content", "video_file", "order")
        read_only_fields = ("module",)

class CourseAssignmentAtomicSerializer(serializers.ModelSerializer):
    class Meta:
        model = CourseAssignment
        fields = ('id', 'module', 'title', 'description', 'due_date', 'max_score')
        read_only_fields = ("module",)

class QuizAtomicSerializer(serializers.ModelSerializer):
    class Meta:
        model = Quiz
        fields = ('id', 'lesson', 'title', 'description', 'order', 'max_score', 'time_limit_minutes', 'max_attempts')
        read_only_fields = ("lesson",)


class EnrollmentManagerSerializer(serializers.ModelSerializer):
    """For tutors to view and manage enrolled students."""
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)

    class Meta:
        model = Enrollment
        fields = (
            "id", "user_name", "user_email", "role", "status", "date_joined"
        )
        read_only_fields = ("user_name", "user_email", "date_joined")


class CourseManagementDashboardSerializer(serializers.ModelSerializer):
    modules = ModuleTutorDetailSerializer(many=True, read_only=True)
    assignments_summary = serializers.SerializerMethodField()
    quizzes_summary = serializers.SerializerMethodField()
    enrollments = EnrollmentManagerSerializer(many=True, read_only=True)
    live_classes = LiveClassMinimalSerializer(many=True, read_only=True)
    global_category = serializers.SerializerMethodField()
    thumbnail = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = (
            "id",
            "slug",
            "title",
            "status",
            "price",
            "short_description",
            "long_description",
            "learning_objectives",
            "thumbnail",
            "promo_video",
            "org_category",
            "org_level",
            "global_subcategory",
            "global_level",
            "global_category",
            "modules",
            "assignments_summary",
            "quizzes_summary",
            "enrollments",
            "live_classes",
            "is_public"
        )

    def get_thumbnail(self, obj):
        if obj.thumbnail:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.thumbnail.url)
            return obj.thumbnail.url
        return None

    def get_global_category(self, obj):
        return obj.global_subcategory.category_id if obj.global_subcategory else None

    def get_assignments_summary(self, obj):
        assignments = CourseAssignment.objects.filter(module__course=obj)
        summary = []
        for assignment in assignments:
            total = assignment.submissions.count()
            pending = assignment.submissions.filter(submission_status="pending").count()
            summary.append({
                "id": assignment.id,
                "title": assignment.title,
                "module_title": assignment.module.title,
                "total_submissions": total,
                "pending_review": pending,
            })
        return summary

    def get_quizzes_summary(self, obj):
        quizzes = Quiz.objects.filter(lesson__module__course=obj)
        summary = []
        for quiz in quizzes:
            total = quiz.attempts.count()
            requires_review = quiz.attempts.filter(requires_review=True, is_completed=True).count()
            summary.append({
                "id": quiz.id,
                "title": quiz.title,
                "lesson_title": quiz.lesson.title,
                "total_attempts": total,
                "requires_review": requires_review,
            })
        return summary


class PopularCourseMinimalSerializer(serializers.ModelSerializer):
    active_enrollment_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Course
        fields = [
            'slug',
            'title',
            'thumbnail',
            'short_description',
            'rating_avg',
            'num_ratings',
            'price',
            'active_enrollment_count',
        ]
        read_only_fields = fields