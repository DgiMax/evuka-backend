import json
import os
import random
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.conf import settings
from django.db.models import Sum, Case, When
from django.http import QueryDict

from books.models import BookAccess
from live.serializers import LiveClassStudentSerializer, LiveClassManagementSerializer
from .models import (
    Course, Module, Lesson, GlobalCategory, GlobalLevel, GlobalSubCategory,
    LessonProgress, Quiz, Question, Option, CourseAssignment, QuizAttempt,
    Answer, AssignmentSubmission, Enrollment, CourseNote, CourseQuestion,
    CourseReply, LessonResource
)
from users.models import CreatorProfile
from books.serializers import BookListSerializer

User = get_user_model()


class InstructorSummarySerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    creator_name = serializers.CharField(source='display_name', read_only=True)
    profile_image = serializers.ImageField(read_only=True)

    class Meta:
        model = CreatorProfile
        fields = ("id", "creator_name", "bio", "username", "profile_image")


class GlobalCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = GlobalCategory
        fields = ("name", "slug")


class GlobalSubCategorySerializer(serializers.ModelSerializer):
    category = GlobalCategorySerializer(read_only=True)

    class Meta:
        model = GlobalSubCategory
        fields = ("name", "slug", "category")


class GlobalLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = GlobalLevel
        fields = ("name",)


class LessonResourceSerializer(serializers.ModelSerializer):
    book_id = serializers.UUIDField(write_only=True, required=False)
    book_details = serializers.SerializerMethodField()
    access_status = serializers.SerializerMethodField()

    class Meta:
        model = LessonResource
        fields = (
            'id', 'title', 'description', 'resource_type', 'order',
            'file', 'external_url', 'course_book', 'book_id',
            'reading_instructions', 'book_details', 'access_status'
        )
        read_only_fields = ('id', 'book_details', 'access_status', 'course_book')

    def get_book_details(self, obj):
        if obj.resource_type == 'book_ref' and obj.course_book:
            return BookListSerializer(obj.course_book.book, context=self.context).data
        return None

    def get_access_status(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return {'has_access': False, 'reason': 'not_logged_in'}

        if obj.resource_type == 'book_ref' and obj.course_book:
            user = request.user
            book = obj.course_book.book

            if BookAccess.objects.filter(user=user, book=book).exists():
                return {'has_access': True, 'reason': 'owned'}

            if obj.course_book.integration_type == 'included':
                return {'has_access': True, 'reason': 'included_in_course'}

            return {
                'has_access': False,
                'reason': 'purchase_required',
                'price': str(book.price),
                'currency': book.currency,
                'buy_url': f"/books/{book.slug}"
            }

        return {'has_access': True}

    def validate(self, attrs):
        if attrs.get('resource_type') == 'book_ref' and not attrs.get('book_id'):
            if not self.instance or not self.instance.course_book:
                raise serializers.ValidationError({"book_id": "A book must be selected for book references."})
        return attrs

    def create(self, validated_data):
        book_uuid = validated_data.pop('book_id', None)
        instance = super().create(validated_data)

        if book_uuid and instance.lesson and instance.lesson.module:
            try:
                from courses.utils import get_or_create_course_book
                course = instance.lesson.module.course
                user = self.context['request'].user
                cb = get_or_create_course_book(course, book_uuid, user)
                instance.course_book = cb
                instance.save()
            except Exception:
                pass
        return instance

    def update(self, instance, validated_data):
        book_uuid = validated_data.pop('book_id', None)
        instance = super().update(instance, validated_data)

        if book_uuid and instance.lesson and instance.lesson.module:
            try:
                from courses.utils import get_or_create_course_book
                course = instance.lesson.module.course
                user = self.context['request'].user
                cb = get_or_create_course_book(course, book_uuid, user)
                instance.course_book = cb
                instance.save()
            except Exception:
                pass
        return instance


class LessonBaseSerializer(serializers.ModelSerializer):
    resources = LessonResourceSerializer(many=True, read_only=True)

    class Meta:
        model = Lesson
        fields = ("id", "title", "is_preview", "estimated_duration_minutes", "video_file", "resources")


class LessonBriefSerializer(LessonBaseSerializer):
    pass


class ModuleBaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Module
        fields = ("id", "title", "description", "order")


class CourseListSerializer(serializers.ModelSerializer):
    instructor_name = serializers.CharField(source='creator_profile.user.get_full_name', read_only=True)
    instructors = serializers.SerializerMethodField()
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
            "instructor_name", "instructors", "is_enrolled", "rating_avg",
            "price", "num_students", "category", "level",
            "status", "status_display", "progress"
        )

    def get_instructors(self, obj):
        return [user.get_full_name() for user in obj.instructors.all()]


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
    instructors = serializers.SerializerMethodField()
    modules = ModuleDetailSerializer(many=True, read_only=True)
    category = GlobalSubCategorySerializer(source="global_subcategory", read_only=True)
    level = GlobalLevelSerializer(source="global_level", read_only=True)
    organization_name = serializers.CharField(source="organization.name", read_only=True)
    is_enrolled = serializers.BooleanField(read_only=True)
    num_students = serializers.IntegerField(read_only=True)
    status = serializers.CharField(read_only=True)
    live_classes = LiveClassStudentSerializer(many=True, read_only=True)

    class Meta:
        model = Course
        fields = (
            "slug", "title", "short_description", "long_description",
            "learning_objectives", "thumbnail",
            "promo_video",
            "instructor", "instructors", "organization_name", "category", "level",
            "price", "rating_avg", "num_students", "num_ratings",
            "is_enrolled", "modules", "status", "created_at", "updated_at",
            "live_classes",
        )

    def get_instructors(self, obj):
        profiles = CreatorProfile.objects.filter(user__in=obj.instructors.all())
        return InstructorSummarySerializer(profiles, many=True).data

    def to_representation(self, instance):
        data = super().to_representation(instance)

        if 'request' in self.context and 'live_classes' in data:
            live_classes_qs = instance.live_classes.all()
            data['live_classes'] = LiveClassStudentSerializer(
                live_classes_qs,
                many=True,
                context=self.context
            ).data
        return data


class QuizAttemptMinimalSerializer(serializers.ModelSerializer):
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
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None
        user = request.user
        latest_attempt = obj.attempts.filter(user=user).order_by('-attempt_number').first()
        if latest_attempt:
            return QuizAttemptMinimalSerializer(latest_attempt).data
        return None


class ExistingAnswerSerializer(serializers.ModelSerializer):
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
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None
        user = request.user
        latest_submission = obj.submissions.filter(user=user).order_by('-submitted_at').first()
        if latest_submission:
            return AssignmentSubmissionMinimalSerializer(latest_submission).data
        return None


class AssignmentSubmissionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssignmentSubmission
        fields = ('file', 'text_submission')

    def validate(self, data):
        if not data.get('file') and not data.get('text_submission'):
            raise serializers.ValidationError("You must submit either a file or text content.")
        if 'text_submission' in data and data['text_submission'] == '':
            data['text_submission'] = None
        return data


class LessonLearningSerializer(serializers.ModelSerializer):
    is_completed = serializers.SerializerMethodField()
    last_watched_timestamp = serializers.SerializerMethodField()
    quizzes = QuizLearningSerializer(many=True, read_only=True)
    resources = LessonResourceSerializer(many=True, read_only=True)

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
    modules = ModuleLearningSerializer(many=True, read_only=True)
    live_classes = LiveClassStudentSerializer(many=True, read_only=True)
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
        data = super().to_representation(instance)

        if 'request' in self.context and 'live_classes' in data:
            live_classes_qs = instance.live_classes.all()
            data['live_classes'] = LiveClassStudentSerializer(
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
    text = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = Option
        fields = ('id', 'text', 'is_correct')


class QuestionCreateUpdateSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    text = serializers.CharField(required=False, allow_blank=True)
    options = OptionCreateUpdateSerializer(many=True, required=False, allow_null=True)

    class Meta:
        model = Question
        fields = (
            'id', 'text', 'question_type', 'score_weight',
            'order', 'instructor_hint', 'options'
        )


class QuizCreateUpdateSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    questions = QuestionCreateUpdateSerializer(many=True, required=False, allow_null=True)
    title = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = Quiz
        fields = (
            'id', 'title', 'description', 'order', 'max_score',
            'time_limit_minutes', 'max_attempts', 'questions'
        )

    def create(self, validated_data):
        questions_data = validated_data.pop('questions', []) or []
        quiz = Quiz.objects.create(**validated_data)

        for q_data in questions_data:
            options_data = q_data.pop('options', []) or []

            if q_data.get('score_weight') is None:
                q_data['score_weight'] = 1

            question = Question.objects.create(quiz=quiz, **q_data)
            for o_data in options_data:
                Option.objects.create(question=question, **o_data)

        return quiz

    def update(self, instance, validated_data):
        questions_data = validated_data.pop('questions', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if questions_data is not None:
            keep_question_ids = []
            for q_data in questions_data:
                options_data = q_data.pop('options', []) or []
                q_id = q_data.get('id')

                if q_id:
                    question = Question.objects.filter(id=q_id, quiz=instance).first()
                    if question:
                        for q_attr, q_val in q_data.items():
                            if q_attr == 'score_weight' and q_val is None:
                                q_val = 1
                            setattr(question, q_attr, q_val)
                        question.save()
                    else:
                        if q_data.get('score_weight') is None:
                            q_data['score_weight'] = 1
                        question = Question.objects.create(quiz=instance, **q_data)
                else:
                    if q_data.get('score_weight') is None:
                        q_data['score_weight'] = 1
                    question = Question.objects.create(quiz=instance, **q_data)

                keep_question_ids.append(question.id)

                keep_option_ids = []
                for o_data in options_data:
                    o_id = o_data.get('id')
                    if o_id:
                        option = Option.objects.filter(id=o_id, question=question).first()
                        if option:
                            for o_attr, o_val in o_data.items():
                                setattr(option, o_attr, o_val)
                            option.save()
                        else:
                            option = Option.objects.create(question=question, **o_data)
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
    resources = LessonResourceSerializer(many=True, required=False)

    class Meta:
        model = Lesson
        fields = ("title", "content", "video_file", "quizzes", "resources", "estimated_duration_minutes", "is_preview")


class ModuleCreateUpdateSerializer(serializers.ModelSerializer):
    lessons = LessonCreateUpdateSerializer(many=True)
    assignments = CourseAssignmentCreateUpdateSerializer(many=True, required=False)

    class Meta:
        model = Module
        fields = ("title", "description", "lessons", "assignments")


class LessonTutorDetailSerializer(serializers.ModelSerializer):
    video_file = serializers.SerializerMethodField()
    quizzes = QuizCreateUpdateSerializer(many=True, read_only=True)
    resources = LessonResourceSerializer(many=True, read_only=True)

    class Meta:
        model = Lesson
        fields = ('id', 'title', 'content', 'video_file', 'quizzes', 'resources')

    def get_video_file(self, obj):
        if obj.video_file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.video_file.url)
            return obj.video_file.url
        return None


class ModuleTutorDetailSerializer(serializers.ModelSerializer):
    lessons = LessonTutorDetailSerializer(many=True, read_only=True)
    assignments = CourseAssignmentCreateUpdateSerializer(many=True, read_only=True)

    class Meta:
        model = Module
        fields = ('id', 'title', 'description', 'lessons', 'assignments')


class TutorCourseDetailSerializer(serializers.ModelSerializer):
    global_category = serializers.SerializerMethodField()
    modules = ModuleTutorDetailSerializer(many=True, read_only=True)
    thumbnail = serializers.SerializerMethodField()
    instructors = serializers.SerializerMethodField()

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
            "modules", "is_public",
            "instructors"
        )

    def get_global_category(self, obj):
        if obj.global_subcategory:
            return obj.global_subcategory.category_id
        return None

    def get_thumbnail(self, obj):
        if obj.thumbnail:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.thumbnail.url)
            return obj.thumbnail.url
        return None

    def get_instructors(self, obj):
        return [user.id for user in obj.instructors.all()]


class CourseCreateUpdateSerializer(serializers.ModelSerializer):
    thumbnail = serializers.ImageField(required=False, allow_null=True)
    modules = serializers.CharField(write_only=True, required=False)
    learning_objectives = serializers.CharField(write_only=True, required=False)
    status = serializers.ChoiceField(choices=Course.COURSE_STATUS_CHOICES, default="draft")
    global_category = serializers.PrimaryKeyRelatedField(
        queryset=GlobalCategory.objects.all(), write_only=True, required=False, allow_null=True
    )
    is_public = serializers.BooleanField(required=False)
    instructors = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), many=True, required=False
    )

    class Meta:
        model = Course
        fields = (
            "title", "short_description", "long_description",
            "learning_objectives",
            "global_subcategory", "global_level",
            "global_category",
            "org_category", "org_level", "thumbnail", "promo_video",
            "price", "status", "is_public", "modules", "instructors"
        )

    def to_internal_value(self, data):
        if hasattr(data, 'copy'):
            data = data.copy()

        optional_fields = [
            'global_category', 'global_subcategory', 'global_level',
            'org_category', 'org_level', 'price'
        ]

        for field in optional_fields:
            if field in data and data[field] == "":
                data.pop(field)

        return super().to_internal_value(data)

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
        return objectives_data

    def validate(self, data):
        if data.get('status') == 'draft':
            return data

        is_org_course = self.context.get('is_organization_course', False)
        errors = {}

        global_subcategory = data.get("global_subcategory")
        global_level = data.get("global_level")
        org_category = data.get("org_category")
        org_level = data.get("org_level")

        if is_org_course:
            if not global_subcategory:
                errors['global_subcategory'] = "Global subcategory is required."
            if not global_level:
                errors['global_level'] = "Global level is required."
            if not org_category:
                errors['org_category'] = "Organization category is required."
            if not org_level:
                errors['org_level'] = "Organization level is required."
        else:
            if not global_subcategory:
                errors['global_subcategory'] = "Global subcategory is required."
            if not global_level:
                errors['global_level'] = "Global level is required."

            if 'org_category' in data: data['org_category'] = None
            if 'org_level' in data: data['org_level'] = None

        if errors:
            raise serializers.ValidationError(errors)

        return data

    def _create_modules(self, course, modules_data, request):
        request_files = request.FILES
        from courses.utils import get_or_create_course_book

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
                resources_data = lesson_data.pop("resources", [])

                file_key_or_path = lesson_data.pop('video_file', None)
                lesson_kwargs = lesson_data.copy()

                if file_key_or_path and file_key_or_path in request_files:
                    lesson_kwargs['video_file'] = request_files[file_key_or_path]
                elif file_key_or_path and isinstance(file_key_or_path, str) and file_key_or_path.startswith("http"):
                    pass
                else:
                    lesson_kwargs['video_file'] = None

                lesson_kwargs.pop('id', None)
                lesson = Lesson.objects.create(module=module, **lesson_kwargs)

                for res_data in resources_data:
                    res_data.pop('id', None)
                    res_file_key = res_data.pop('file', None)
                    if res_file_key and res_file_key in request_files:
                        res_data['file'] = request_files[res_file_key]

                    book_uuid = res_data.pop('book_id', None) or res_data.pop('course_book', None)
                    if book_uuid:
                        try:
                            course_book_instance = get_or_create_course_book(course, book_uuid, request.user)
                            res_data['course_book'] = course_book_instance
                        except Exception:
                            pass

                    LessonResource.objects.create(lesson=lesson, **res_data)

                for quiz_data in quizzes_data:
                    questions_data = quiz_data.pop("questions", [])
                    quiz_data.pop('id', None)
                    quiz = Quiz.objects.create(lesson=lesson, **quiz_data)

                    for question_data in questions_data:
                        options_data = question_data.pop("options", [])
                        question_data.pop('id', None)

                        if question_data.get('score_weight') is None:
                            question_data['score_weight'] = 1

                        question = Question.objects.create(quiz=quiz, **question_data)

                        for option_data in options_data:
                            option_data.pop('id', None)
                            Option.objects.create(question=question, **option_data)

    def create(self, validated_data):
        modules_data = validated_data.pop("modules", [])
        objectives_data = validated_data.pop("learning_objectives", [])
        instructors = validated_data.pop("instructors", [])

        validated_data.pop("global_category", None)

        validated_data["learning_objectives"] = [
            obj["value"] for obj in objectives_data if isinstance(obj, dict) and obj.get("value")
        ]

        request = self.context.get('request')
        course = Course.objects.create(**validated_data)

        if instructors:
            course.instructors.set(instructors)

        self._create_modules(course, modules_data, request)
        return course

    def update(self, instance, validated_data):
        modules_data = validated_data.pop("modules", None)
        objectives_data = validated_data.pop("learning_objectives", None)
        instructors = validated_data.pop("instructors", None)

        validated_data.pop("global_category", None)

        request = self.context.get('request')

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if objectives_data is not None:
            instance.learning_objectives = [
                obj["value"] for obj in objectives_data if isinstance(obj, dict) and obj.get("value")
            ]

        if instructors is not None:
            instance.instructors.set(instructors)

        if modules_data is not None:
            instance.modules.all().delete()
            self._create_modules(instance, modules_data, request)

        instance.save()
        return instance


class LessonPreviewSerializer(serializers.ModelSerializer):
    resources = LessonResourceSerializer(many=True, read_only=True)

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
    live_classes = LiveClassStudentSerializer(many=True, read_only=True)

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
        data = super().to_representation(instance)

        if 'request' in self.context and 'live_classes' in data:
            live_classes_qs = instance.live_classes.all()
            data['live_classes'] = LiveClassStudentSerializer(
                live_classes_qs,
                many=True,
                context=self.context
            ).data
        return data


class AnswerSubmissionSerializer(serializers.Serializer):
    answer_id = serializers.PrimaryKeyRelatedField(
        queryset=Answer.objects.all(),
        source='id'
    )
    selected_option_id = serializers.IntegerField(required=False, allow_null=True)
    user_answer_text = serializers.CharField(required=False, allow_blank=True)

    def validate_answer_id(self, value):
        attempt = self.context.get('attempt')
        if value.attempt != attempt:
            raise serializers.ValidationError("Answer does not belong to the current attempt.")
        return value


class QuizAttemptSubmissionSerializer(serializers.Serializer):
    answers = AnswerSubmissionSerializer(many=True)

    def save(self):
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
    full_name = serializers.CharField(source='get_full_name', read_only=True)

    class Meta:
        model = User
        fields = ('id', 'full_name')


class AssignmentSubmissionManagerSerializer(serializers.ModelSerializer):
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
    class Meta:
        model = AssignmentSubmission
        fields = ("grade", "feedback", "submission_status")

    def validate_grade(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("Grade cannot be negative.")
        return value


class QuizAttemptManagerSerializer(serializers.ModelSerializer):
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
    content = serializers.CharField(required=False, allow_blank=True)
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
    live_classes = LiveClassManagementSerializer(many=True, read_only=True)
    global_category = serializers.SerializerMethodField()
    thumbnail = serializers.SerializerMethodField()
    instructors = serializers.SerializerMethodField()

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
            "is_public",
            "instructors"
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

    def get_instructors(self, obj):
        return [user.id for user in obj.instructors.all()]

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