from django.db.models import Count, Q, Exists, OuterRef, Max, Case, When, Value, BooleanField
from rest_framework import viewsets, mixins, status, permissions, serializers, generics
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.views import APIView
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.shortcuts import get_object_or_404
from weasyprint import HTML
from django.utils import timezone
from rest_framework.parsers import MultiPartParser, FormParser
from django.db import transaction

from organizations.models import OrgCategory, OrgLevel, OrgMembership
from .models import (
    Certificate,
    LessonProgress,
    Lesson,
    Course,
    Enrollment,
    GlobalCategory,
    GlobalSubCategory,
    GlobalLevel, Answer, Option, QuizAttempt, Question, Quiz, Module, AssignmentSubmission, CourseAssignment,
    CourseNote, CourseQuestion, LessonResource,
)
from .permissions import IsEnrolled, IsTutorOrOrgAdmin
from .filters import CourseFilter
from .serializers import (
    CourseListSerializer,
    CourseDetailSerializer,
    CourseLearningSerializer,
    CourseCreateUpdateSerializer, CoursePreviewSerializer, TutorCourseDetailSerializer, QuizAttemptSubmissionSerializer,
    EnrollmentManagerSerializer, QuizAttemptManagerSerializer, AssignmentSubmissionManagerSerializer,
    GradeAssignmentSerializer, LessonCreateAtomicSerializer, ModuleAtomicSerializer,
    CourseManagementDashboardSerializer, CourseAssignmentAtomicSerializer, PopularCourseMinimalSerializer,
    QuizQuestionLearningSerializer, ExistingAnswerSerializer, AssignmentSubmissionCreateSerializer,
    CourseNoteSerializer, CourseReplySerializer, CourseQuestionSerializer, QuizCreateUpdateSerializer,
    LessonResourceSerializer
)
from .services import CourseProgressService


class CourseViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """
    Public/Student-facing viewset. Filters courses by the student's
    assigned OrgLevel when in organization context.
    """

    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [permissions.AllowAny]
    lookup_field = "slug"
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = CourseFilter
    search_fields = ["title", "short_description", "creator_profile__user__first_name"]
    ordering_fields = ["created_at", "rating_avg", "price"]

    def get_serializer_class(self):
        """Returns the appropriate serializer based on the action."""
        if self.action == "most_popular":
            return PopularCourseMinimalSerializer
        if self.action == "list":
            return CourseListSerializer
        if self.action == "learn":
            return CourseLearningSerializer
        return CourseDetailSerializer

    def get_queryset(self):
        """
        Retrieves the base queryset, filters by organization/public status,
        and applies the organizational level filter if active_org is set.
        """
        user = self.request.user
        active_org = getattr(self.request, "active_organization", None)

        queryset = Course.objects.published()

        if active_org:
            queryset = queryset.filter(organization=active_org)

            if user.is_authenticated:
                user_membership = OrgMembership.objects.filter(
                    user=user,
                    organization=active_org,
                    is_active=True,
                    role='student'
                ).select_related('level').first()

                if user_membership and user_membership.level:
                    user_level = user_membership.level
                    queryset = queryset.filter(Q(org_level=user_level))

        else:
            queryset = queryset.filter(
                Q(organization__isnull=True) | Q(is_public=True),
            )

        queryset = queryset.annotate(
            num_students=Count(
                "enrollments",
                filter=Q(enrollments__status="active"),
                distinct=True,
            )
        )

        if self.action == 'list' and user.is_authenticated:
            enrolled_course_ids = Enrollment.objects.filter(
                user=user,
                status__in=['active', 'completed']
            ).values_list('course_id', flat=True)

            queryset = queryset.exclude(id__in=enrolled_course_ids)

        if self.action == "most_popular":
            return queryset.order_by("-num_students", "-rating_avg")[:4]

        if user.is_authenticated:
            user_enrollment = Enrollment.objects.filter(
                course=OuterRef("pk"),
                user=user,
                status="active",
            )
            queryset = queryset.annotate(is_enrolled=Exists(user_enrollment))
        else:
            queryset = queryset.annotate(
                is_enrolled=Exists(Enrollment.objects.none())
            )

        if self.action == "list":
            queryset = queryset.order_by("-created_at")
            return queryset.select_related(
                "creator_profile__user",
                "global_subcategory__category",
                "global_level",
                "organization",
                "org_category",
                "org_level",
            )

        if self.action in ["retrieve", "learn"]:
            queryset = queryset.prefetch_related("modules__lessons__resources", "live_classes__lessons")
            return queryset.select_related(
                "organization",
                "creator_profile__user",
                "global_subcategory__category",
                "global_level",
                "org_category",
                "org_level",
            )

        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        filterset = self.filterset_class(request.query_params, queryset=queryset, request=request)

        if not filterset.is_valid():
            pass

        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(
        detail=False,
        methods=["get"],
        permission_classes=[permissions.AllowAny],
        url_path="most-popular",
    )
    def most_popular(self, request):
        """Retrieves the top 4 most popular published courses based on active enrollments."""
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(
        detail=True,
        methods=["get"],
        permission_classes=[permissions.IsAuthenticated, IsEnrolled],
        url_path="learn",
    )
    def learn(self, request, slug=None):
        queryset = self.get_queryset().prefetch_related(
            'modules__lessons__resources__course_book__book',
            'modules__lessons__quizzes__attempts',
            'modules__assignments__submissions',
            'live_classes__lessons'
        )
        course = get_object_or_404(queryset, slug=slug)
        serializer = CourseLearningSerializer(course, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=["get"], permission_classes=[permissions.IsAuthenticated], url_path="progress-report")
    def progress_report(self, request, slug=None):
        course = self.get_object()
        service = CourseProgressService(request.user, course)
        data = service.calculate_progress()
        return Response(data)


class CourseNoteViewSet(viewsets.GenericViewSet):
    serializer_class = CourseNoteSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=['get', 'patch'], url_path='(?P<course_slug>[^/.]+)')
    def manage_note(self, request, course_slug=None):
        """
        GET: Retrieves the user's note for the specified course (creating an empty one if necessary).
        PATCH: Auto-saves the HTML content sent by the editor.
        """
        user = request.user

        course = get_object_or_404(Course, slug=course_slug)

        note, created = CourseNote.objects.get_or_create(
            user=user,
            course=course,
            defaults={'content': '<p></p>'}
        )

        if request.method == 'GET':
            serializer = self.get_serializer(note)
            return Response(serializer.data, status=status.HTTP_200_OK)

        if request.method == 'PATCH':
            serializer = self.get_serializer(note, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()

            return Response(serializer.data, status=status.HTTP_200_OK)

        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)


class CourseDiscussionViewSet(viewsets.ModelViewSet):
    serializer_class = CourseQuestionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        qs = CourseQuestion.objects.all()

        qs = qs.annotate(
            is_mine=Case(
                When(user=user, then=Value(True)),
                default=Value(False),
                output_field=BooleanField()
            )
        )

        if self.action == 'list':
            course_slug = self.request.query_params.get('course_slug')
            if not course_slug:
                return CourseQuestion.objects.none()
            qs = qs.filter(course__slug=course_slug)

        return qs.order_by('-is_mine', '-created_at').select_related('user').prefetch_related('replies__user')

    def perform_create(self, serializer):
        course_slug = self.request.data.get('course_slug')
        course = get_object_or_404(Course, slug=course_slug)
        serializer.save(user=self.request.user, course=course)

    @action(detail=True, methods=['post'])
    def reply(self, request, pk=None):
        question = self.get_object()

        if question.user == request.user:
            return Response(
                {"error": "You cannot reply to your own question."},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = CourseReplySerializer(data=request.data)
        if serializer.is_valid():
            is_instructor = (question.course.creator == request.user)

            serializer.save(
                user=request.user,
                question=question,
                is_instructor=is_instructor
            )
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TutorCourseViewSet(viewsets.ModelViewSet):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "slug"
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["status"]

    search_fields = ["title", "short_description"]
    ordering_fields = ["created_at", "rating_avg"]

    def get_permissions(self):
        if self.action in ["create", "update", "partial_update", "update_status"]:
            active_org = getattr(self.request, "active_organization", None)
            if active_org:
                return [permissions.IsAuthenticated(), IsTutorOrOrgAdmin()]
        return [permissions.IsAuthenticated()]

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return CourseCreateUpdateSerializer
        if self.action == "retrieve":
            return TutorCourseDetailSerializer
        return CourseListSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        active_org = getattr(self.request, "active_organization", None)
        is_org_course = bool(active_org)

        if self.action in ['update', 'partial_update']:
            try:
                course = self.get_object()
                if course.organization:
                    is_org_course = True
            except Exception:
                pass

        context['is_organization_course'] = is_org_course
        return context

    def get_queryset(self):
        user = self.request.user
        active_org = getattr(self.request, "active_organization", None)

        queryset = (
            Course.objects.select_related(
                "organization",
                "creator_profile__user",
                "global_subcategory",
                "global_level",
                "org_category",
                "org_level",
            )
            .prefetch_related("modules__lessons", "live_classes__lessons")
            .order_by("-created_at")
        )

        if active_org:
            membership = OrgMembership.objects.filter(
                user=user, organization=active_org
            ).first()

            if membership and membership.role in ["admin", "owner"]:
                return queryset.filter(organization=active_org)
            else:
                return queryset.filter(
                    Q(organization=active_org) &
                    (Q(creator=user) | Q(instructors__in=[user]))
                ).distinct()

        return queryset.filter(
            Q(creator_profile__user=user) | Q(instructors__in=[user]),
            organization__isnull=True,
        ).distinct()

    def retrieve(self, request, *args, **kwargs):
        course = self.get_object()
        serializer = self.get_serializer(course)
        return Response(serializer.data)

    def perform_create(self, serializer):
        active_org = getattr(self.request, "active_organization", None)
        user = self.request.user

        if active_org:
            serializer.save(
                organization=active_org,
                creator=user,
                creator_profile=None,
            )
        else:
            creator_profile = getattr(user, "creator_profile", None)
            if not creator_profile:
                raise serializers.ValidationError(
                    "User does not have a Creator Profile to create personal courses."
                )
            serializer.save(
                organization=None,
                creator=user,
                creator_profile=creator_profile,
            )

    def perform_update(self, serializer):
        serializer.save()

    @action(
        detail=True,
        methods=["patch"],
        permission_classes=[permissions.IsAuthenticated, IsTutorOrOrgAdmin],
        url_path="update-status",
    )
    def update_status(self, request, slug=None):
        course = self.get_object()
        user = request.user
        new_status = request.data.get("status")

        if new_status not in dict(Course.COURSE_STATUS_CHOICES):
            return Response(
                {"error": f"Invalid status '{new_status}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        active_org = getattr(request, "active_organization", None)
        if active_org:
            membership = OrgMembership.objects.filter(
                user=user, organization=active_org
            ).first()
            if not membership:
                return Response(
                    {"error": "You are not a member of this organization."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if new_status == "published" and not membership.is_admin_or_owner():
                return Response(
                    {
                        "error": "Tutors cannot publish organization courses. Only admins or owners can."
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        course.status = new_status
        course.save()

        return Response(
            {
                "message": f"Course status updated to '{new_status}'.",
                "slug": course.slug,
                "status": course.status,
            },
            status=status.HTTP_200_OK,
        )

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[permissions.IsAuthenticated, IsTutorOrOrgAdmin],
        url_path="archive"
    )
    def archive_course(self, request, slug=None):
        course = self.get_object()

        if course.status == 'archived':
            course.status = 'archived'
            message = "Course unarchived (moved to Draft)."
        else:
            course.status = 'archived'
            message = "Course archived."

        course.save()

        return Response({
            "message": message,
            "status": course.status,
            "slug": course.slug
        }, status=status.HTTP_200_OK)


class FilterOptionsView(APIView):
    """
    Provides the frontend with the necessary data to build the filter sidebar.
    Context-aware between global and organization courses.
    """
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        active_org = getattr(request, "active_organization", None)

        # 1. Global Categories (Parents) - Added thumbnail
        global_categories = GlobalCategory.objects.all().order_by("name")
        global_categories_data = [{
            "id": str(cat.id),
            "name": cat.name,
            "slug": cat.slug,
            "thumbnail": request.build_absolute_uri(cat.thumbnail.url) if cat.thumbnail else None
        } for cat in global_categories]

        # 2. Global Subcategories - Added parent_slug for frontend matching
        global_subcategories = GlobalSubCategory.objects.all().select_related('category').order_by("category__name", "name")
        global_subcategories_data = [{
            "id": str(sub.id),
            "name": sub.name,
            "slug": sub.slug,
            "parent_id": str(sub.category_id),
            "parent_slug": sub.category.slug  # <--- NEW: Vital for the drill-down logic
        } for sub in global_subcategories]

        global_levels = GlobalLevel.objects.all().order_by("order")
        global_levels_data = [{"id": str(lvl.name), "name": lvl.name} for lvl in global_levels]

        # Organization Logic
        if active_org:
            org_categories = OrgCategory.objects.filter(organization=active_org).order_by("name")
            org_levels = OrgLevel.objects.filter(organization=active_org).order_by("order")

            org_categories_data = [{"id": str(cat.id), "name": cat.name} for cat in org_categories]
            org_levels_data = [{"id": str(lvl.id), "name": lvl.name} for lvl in org_levels]

            course_qs = Course.objects.filter(
                organization=active_org
            )

            data = {
                "orgCategories": org_categories_data,
                "orgLevels": org_levels_data,

                "globalCategories": global_categories_data,
                "globalSubCategories": global_subcategories_data,
                "globalLevels": global_levels_data,

                "context": "organization",
            }

        else:
            course_qs = Course.objects.filter(
                organization__isnull=True
            )
            data = {
                "globalCategories": global_categories_data,
                "globalSubCategories": global_subcategories_data,
                "globalLevels": global_levels_data,

                "orgCategories": [],
                "orgLevels": [],

                "context": "global",
            }

        # Price Calculation
        max_price_agg = course_qs.aggregate(max_p=Max("price"))
        max_price = int(max_price_agg["max_p"]) if max_price_agg["max_p"] else 5000

        data["price"] = {"min": 0, "max": max_price}
        return Response(data)


def download_certificate(request, certificate_uid):
    """Generate and download a course completion certificate as PDF."""
    certificate = get_object_or_404(Certificate, certificate_uid=certificate_uid)
    html_string = render_to_string("certificates/template.html", {"certificate": certificate})
    pdf = HTML(string=html_string).write_pdf()

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="certificate-{certificate.course.slug}.pdf"'
    return response


class LessonViewSet(viewsets.GenericViewSet):
    """
    Handles interactions with a single lesson (e.g., tracking progress).
    Context-aware and permission-secure.
    """

    queryset = Lesson.objects.all()
    permission_classes = [IsAuthenticated, IsEnrolled]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Lesson.objects.none()

        user_course_ids = Enrollment.objects.filter(
            user=user, status="active"
        ).values_list("course_id", flat=True)

        queryset = Lesson.objects.filter(module__course_id__in=user_course_ids)

        active_org = getattr(self.request, "active_organization", None)
        if active_org:
            queryset = queryset.filter(
                Q(module__course__organization=active_org)
                | Q(organization=active_org)
            )
        else:
            queryset = queryset.filter(
                module__course__organization__isnull=True,
                organization__isnull=True,
            )

        return queryset

    @action(detail=True, methods=["post"], url_path="progress")
    def update_progress(self, request, pk=None):
        """Receives and saves user progress for a lesson."""
        lesson = self.get_object()
        user = request.user
        timestamp = request.data.get("timestamp", 0)
        is_completed = request.data.get("completed", False)

        progress, created = LessonProgress.objects.get_or_create(
            user=user, lesson=lesson
        )
        progress.last_watched_timestamp = timestamp

        if is_completed and not progress.is_completed:
            progress.mark_as_completed()
        else:
            progress.save()

        return Response({"status": "progress updated"}, status=status.HTTP_200_OK)


class CourseFormOptionsView(APIView):
    """
    Provides category and level options for the course creation form,
    aware of the active organization context, and structured for cascading dropdowns.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        active_org = getattr(request, "active_organization", None)

        global_categories = GlobalCategory.objects.all().order_by("name")
        global_categories_data = [{
            "id": str(cat.id),
            "name": cat.name,
            "slug": cat.slug
        } for cat in global_categories]

        global_subcategories = GlobalSubCategory.objects.all().select_related('category').order_by("category__name",
                                                                                                   "name")
        global_subcategories_data = [{
            "id": str(sub.id),
            "name": sub.name,
            "slug": sub.slug,
            "parent_id": str(sub.category_id)
        } for sub in global_subcategories]

        global_levels = GlobalLevel.objects.all().order_by("order")
        global_levels_data = [{"id": str(lvl.id), "name": lvl.name} for lvl in global_levels]

        if active_org:
            org_categories = OrgCategory.objects.filter(organization=active_org).order_by("name")
            org_levels = OrgLevel.objects.filter(organization=active_org).order_by("order")

            org_categories_data = [{"id": str(cat.id), "name": cat.name} for cat in org_categories]
            org_levels_data = [{"id": str(lvl.id), "name": lvl.name} for lvl in org_levels]

            data = {
                "orgCategories": org_categories_data,
                "orgLevels": org_levels_data,

                "globalCategories": global_categories_data,
                "globalSubCategories": global_subcategories_data,
                "globalLevels": global_levels_data,

                "context": "organization",
            }
            course_qs = Course.objects.filter(
                organization=active_org
            )

        else:
            data = {
                "globalCategories": global_categories_data,
                "globalSubCategories": global_subcategories_data,
                "globalLevels": global_levels_data,

                "orgCategories": [],
                "orgLevels": [],

                "context": "global",
            }
            course_qs = Course.objects.filter(
                organization__isnull=True
            )

        max_price_agg = course_qs.aggregate(max_p=Max("price"))
        max_price = int(max_price_agg["max_p"]) if max_price_agg["max_p"] else 5000

        data["price"] = {"min": 0, "max": max_price}
        return Response(data)


class CoursePreviewView(generics.RetrieveAPIView):
    """
    Tutor-only view to preview their own course as learners would see it.
    """
    serializer_class = CoursePreviewSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "slug"

    def get_queryset(self):
        user = self.request.user
        return Course.objects.filter(Q(creator_profile__user=user) | Q(instructors__in=[user])).distinct()


class CourseDetailsPreviewView(generics.RetrieveAPIView):
    """
    Tutor-only preview for course details (public marketing view simulation).
    """
    serializer_class = CourseDetailSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "slug"

    def get_queryset(self):
        user = self.request.user
        return Course.objects.filter(Q(creator_profile__user=user) | Q(instructors__in=[user])).distinct()


class QuizAttemptViewSet(viewsets.ViewSet):
    """
    Handles the student workflow for starting and submitting a course quiz.

    Endpoints:
    POST /api/quizzes/{quiz_pk}/start/   -> Starts a new attempt.
    POST /api/quizzes/{attempt_pk}/submit/ -> Submits answers and grades the quiz.
    """
    permission_classes = [permissions.IsAuthenticated]

    def _check_enrollment(self, user, quiz):
        """Helper to ensure the user is actively enrolled in the course."""
        course = quiz.lesson.module.course

        if not Enrollment.objects.filter(user=user, course=course, status="active").exists():
            return Response(
                {"detail": "You must be actively enrolled in the course to take this quiz."},
                status=status.HTTP_403_FORBIDDEN
            )
        return None

    @action(detail=True, methods=['post'], url_path='start')
    @transaction.atomic
    def start_attempt(self, request, pk=None):
        """
        Starts a new QuizAttempt, performs validity checks, and pre-populates Answer records.
        Returns the questions array, including the necessary 'answer_id' for submission.
        """
        quiz = get_object_or_404(Quiz.objects.select_related('lesson__module__course'), pk=pk)
        user = request.user

        enrollment_check = self._check_enrollment(user, quiz)
        if enrollment_check:
            return enrollment_check

        uncompleted_attempt = QuizAttempt.objects.filter(
            quiz=quiz,
            user=user,
            is_completed=False
        ).first()

        last_attempt_number = QuizAttempt.objects.filter(quiz=quiz, user=user).aggregate(Max('attempt_number'))[
                                  'attempt_number__max'] or 0
        next_attempt_number = last_attempt_number + 1

        completed_attempts = QuizAttempt.objects.filter(quiz=quiz, user=user, is_completed=True).count()

        if completed_attempts >= quiz.max_attempts:
            return Response(
                {"detail": f"You have reached the maximum allowed attempts ({quiz.max_attempts})."},
                status=status.HTTP_403_FORBIDDEN
            )

        if uncompleted_attempt:
            new_attempt = uncompleted_attempt
            status_code = status.HTTP_200_OK
        else:
            new_attempt = QuizAttempt.objects.create(
                quiz=quiz,
                user=user,
                max_score=quiz.max_score,
                attempt_number=next_attempt_number
            )
            status_code = status.HTTP_201_CREATED

        questions_qs = Question.objects.filter(quiz=quiz).order_by('order').prefetch_related('options')

        if not questions_qs.exists():
            return Response(
                {"detail": "This quiz has no questions defined by the instructor."},
                status=status.HTTP_400_BAD_REQUEST
            )

        questions_data = []

        for question in questions_qs:
            answer_obj, created = Answer.objects.get_or_create(
                attempt=new_attempt,
                question=question
            )

            q_data = QuizQuestionLearningSerializer(question, context={'request': request}).data

            q_data['answer_id'] = answer_obj.id

            questions_data.append(q_data)

        response_data = {
            "attempt_id": new_attempt.id,
            "quiz_title": quiz.title,
            "questions_count": questions_qs.count(),
            "time_limit_minutes": quiz.time_limit_minutes,
            "questions": questions_data,
        }

        if status_code == status.HTTP_200_OK:
            response_data['detail'] = "Resuming existing attempt."

        return Response(response_data, status=status_code)

    @action(detail=True, methods=['get'], url_path='answers')
    def retrieve_answers(self, request, pk=None):
        """
        GET /quizzes/{attempt_id}/answers/
        Retrieves the user's saved answers for a specific quiz attempt ID (pk).
        Used to pre-fill the form when resuming a quiz.
        """
        attempt = get_object_or_404(QuizAttempt.objects.select_related('quiz'), pk=pk)
        user = request.user

        if attempt.user != user:
            return Response(
                {"detail": "Not authorized to access this attempt's answers."},
                status=status.HTTP_403_FORBIDDEN
            )

        if attempt.is_completed:
            return Response(
                {"detail": "This attempt is already submitted and cannot be edited."},
                status=status.HTTP_400_BAD_REQUEST
            )

        answers_qs = attempt.answers.all().select_related('question')

        serializer = ExistingAnswerSerializer(answers_qs, many=True)

        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='submit')
    @transaction.atomic
    def submit_attempt(self, request, pk=None):
        """
        Submits the student's answers, validates them, grades the quiz,
        and marks the attempt as completed.
        """
        attempt = get_object_or_404(QuizAttempt.objects.select_related('quiz'), pk=pk)

        if attempt.user != request.user:
            return Response({"detail": "Not authorized to submit this attempt."}, status=status.HTTP_403_FORBIDDEN)
        if attempt.is_completed:
            return Response({"detail": "This attempt has already been submitted."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = QuizAttemptSubmissionSerializer(data=request.data, context={'attempt': attempt})
        serializer.is_valid(raise_exception=True)

        score, requires_review = serializer.save()

        return Response({
            "detail": "Quiz submitted and graded.",
            "attempt_id": attempt.id,
            "score": round(score, 2),
            "max_score": attempt.max_score,
            "requires_review": requires_review,
            "percentage": round((score / attempt.max_score) * 100, 2) if attempt.max_score > 0 else 0
        })


class CourseManagerViewSet(viewsets.GenericViewSet, mixins.RetrieveModelMixin):
    queryset = Course.objects.all()
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [permissions.IsAuthenticated, IsTutorOrOrgAdmin]
    lookup_field = "slug"

    def get_course_object(self):
        return self.get_object()

    def retrieve(self, request, slug=None):
        course = self.get_course_object()
        serializer = CourseManagementDashboardSerializer(
            course,
            context={"request": request}
        )
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="modules")
    def create_module(self, request, slug=None):
        course = self.get_course_object()
        serializer = ModuleAtomicSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        max_order = course.modules.aggregate(Max('order'))['order__max']
        order = (max_order or 0) + 1
        module = serializer.save(course=course, order=order)
        return Response(ModuleAtomicSerializer(module).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch", "delete"], url_path="modules/(?P<module_pk>[^/.]+)")
    def manage_module_detail(self, request, slug=None, module_pk=None):
        course = self.get_course_object()
        module = get_object_or_404(course.modules, pk=module_pk)

        if request.method == "DELETE":
            module.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        serializer = ModuleAtomicSerializer(module, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated_module = serializer.save()
        return Response(ModuleAtomicSerializer(updated_module).data)

    @action(detail=True, methods=["post"], url_path="lessons")
    def create_lesson(self, request, slug=None):
        course = self.get_course_object()
        module_id = request.data.get("module")
        module = get_object_or_404(course.modules, pk=module_id)

        serializer = LessonCreateAtomicSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        max_order = module.lessons.aggregate(Max('order'))['order__max']
        order = (max_order or 0) + 1
        lesson = serializer.save(module=module, order=order)
        return Response(LessonCreateAtomicSerializer(lesson).data, status=status.HTTP_201_CREATED)

    @action(
        detail=True,
        methods=["patch", "delete"],
        url_path="lessons/(?P<lesson_pk>[^/.]+)"
    )
    def manage_lesson_detail(self, request, slug=None, lesson_pk=None):
        course = self.get_course_object()
        lesson = get_object_or_404(
            Lesson,
            pk=lesson_pk,
            module__course=course
        )

        if request.method == "DELETE":
            lesson.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        serializer = LessonCreateAtomicSerializer(lesson, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated_lesson = serializer.save()
        return Response(LessonCreateAtomicSerializer(updated_lesson).data)

    @action(detail=True, methods=["post"], url_path="resources")
    def create_resource(self, request, slug=None):
        course = self.get_course_object()
        lesson_id = request.data.get("lesson")
        lesson = get_object_or_404(Lesson, pk=lesson_id, module__course=course)

        serializer = LessonResourceSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)

        max_order = lesson.resources.aggregate(Max('order'))['order__max']
        order = (max_order or 0) + 1

        resource = serializer.save(lesson=lesson, order=order)
        return Response(LessonResourceSerializer(resource).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch", "delete"], url_path="resources/(?P<resource_pk>[^/.]+)")
    def manage_resource_detail(self, request, slug=None, resource_pk=None):
        course = self.get_course_object()
        resource = get_object_or_404(LessonResource, pk=resource_pk, lesson__module__course=course)

        if request.method == "DELETE":
            resource.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        serializer = LessonResourceSerializer(resource, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        updated_resource = serializer.save()
        return Response(LessonResourceSerializer(updated_resource).data)

    @action(
        detail=True,
        methods=["post"],
        url_path="lessons/(?P<lesson_pk>[^/.]+)/quizzes"
    )
    def create_quiz(self, request, slug=None, lesson_pk=None):
        course = self.get_course_object()
        lesson = get_object_or_404(Lesson, pk=lesson_pk, module__course=course)

        serializer = QuizCreateUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        quiz = serializer.save(lesson=lesson)

        return Response(QuizCreateUpdateSerializer(quiz).data, status=status.HTTP_201_CREATED)

    @action(
        detail=True,
        methods=["patch", "delete"],
        url_path="quizzes/(?P<quiz_pk>[^/.]+)"
    )
    def manage_quiz_detail(self, request, slug=None, quiz_pk=None):
        course = self.get_course_object()
        quiz = get_object_or_404(Quiz, pk=quiz_pk, lesson__module__course=course)

        if request.method == "DELETE":
            quiz.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        serializer = QuizCreateUpdateSerializer(quiz, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated_quiz = serializer.save()
        return Response(QuizCreateUpdateSerializer(updated_quiz).data)

    @action(detail=True, methods=["post"], url_path="assignments")
    def create_assignment(self, request, slug=None):
        course = self.get_course_object()
        module_id = request.data.get("module")
        module = get_object_or_404(course.modules, pk=module_id)

        serializer = CourseAssignmentAtomicSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        assignment = serializer.save(module=module)

        return Response(CourseAssignmentAtomicSerializer(assignment).data, status=status.HTTP_201_CREATED)

    @action(
        detail=True,
        methods=["patch", "delete"],
        url_path="assignments/(?P<assignment_pk>[^/.]+)"
    )
    def manage_assignment_detail(self, request, slug=None, assignment_pk=None):
        course = self.get_course_object()
        assignment = get_object_or_404(
            CourseAssignment.objects.filter(module__course=course),
            pk=assignment_pk
        )

        if request.method == "DELETE":
            assignment.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        serializer = CourseAssignmentAtomicSerializer(assignment, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated_assignment = serializer.save()
        return Response(CourseAssignmentAtomicSerializer(updated_assignment).data)

    @action(detail=True, methods=["get"], url_path="submissions-list")
    def list_all_submissions(self, request, slug=None):
        course = self.get_course_object()
        submissions = AssignmentSubmission.objects.filter(
            assignment__module__course=course
        ).order_by("-submitted_at").select_related("user", "assignment", "graded_by")

        submission_status = request.query_params.get("status")
        if submission_status in dict(AssignmentSubmission.SUBMISSION_STATUS_CHOICES):
            submissions = submissions.filter(submission_status=submission_status)

        serializer = AssignmentSubmissionManagerSerializer(
            submissions,
            many=True,
            context={'request': request}
        )
        return Response(serializer.data)

    @action(detail=True, methods=["patch"], url_path="assignments/grade/(?P<submission_pk>[^/.]+)")
    def grade_submission(self, request, slug=None, submission_pk=None):
        course = self.get_course_object()
        submission = get_object_or_404(
            AssignmentSubmission.objects.filter(assignment__module__course=course),
            pk=submission_pk
        )
        serializer = GradeAssignmentSerializer(submission, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        submission = serializer.save(graded_by=request.user, graded_at=timezone.now())

        return Response(AssignmentSubmissionManagerSerializer(submission).data)

    @action(detail=True, methods=["get"], url_path="quizzes/review-attempts")
    def list_review_attempts(self, request, slug=None):
        course = self.get_course_object()
        attempts = QuizAttempt.objects.filter(
            quiz__lesson__module__course=course,
            requires_review=True,
            is_completed=True
        ).order_by("-completed_at").select_related("user", "quiz__lesson")

        serializer = QuizAttemptManagerSerializer(attempts, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["patch"], url_path="enrollments/(?P<enrollment_pk>[^/.]+)")
    def update_enrollment(self, request, slug=None, enrollment_pk=None):
        course = self.get_course_object()
        enrollment = get_object_or_404(course.enrollments, pk=enrollment_pk)

        serializer = EnrollmentManagerSerializer(enrollment, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated_enrollment = serializer.save()

        return Response(EnrollmentManagerSerializer(updated_enrollment).data)


class AssignmentSubmissionViewSet(viewsets.GenericViewSet):
    """
    Handles student submission for a CourseAssignment.
    The submission URL is registered using the assignment ID (PK).
    """
    queryset = CourseAssignment.objects.all()

    parser_classes = [MultiPartParser, FormParser]

    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'pk'

    @action(detail=True, methods=['post'], url_path='submit')
    @transaction.atomic
    def submit(self, request, pk=None):
        """Creates or updates a submission for the given assignment (student action)."""
        assignment = self.get_object()
        user = request.user

        course = assignment.module.course
        if not Enrollment.objects.filter(user=user, course=course, status="active").exists():
            return Response(
                {"detail": "You must be actively enrolled in the course to submit this assignment."},
                status=status.HTTP_403_FORBIDDEN
            )

        submission, created = AssignmentSubmission.objects.get_or_create(
            assignment=assignment,
            user=user,
            defaults={'submission_status': 'pending'}
        )

        if submission.submission_status not in ['pending', 'resubmit'] and not created:
            return Response(
                {"detail": f"Submission status is '{submission.submission_status}'. Wait for instruction."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = AssignmentSubmissionCreateSerializer(
            submission,
            data=request.data,
            partial=True
        )
        serializer.is_valid(raise_exception=True)

        updated_submission = serializer.save(submission_status='pending')

        return Response(AssignmentSubmissionManagerSerializer(updated_submission).data,
                        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class CourseSearchAPIView(APIView):
    """
    Independent API for searching courses a user manages.
    Filters by Organization if org_slug is provided, otherwise searches Personal courses.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        query = request.query_params.get('q', '')
        org_slug = request.query_params.get('org_slug', None)
        user = request.user

        queryset = Course.objects.filter(
            Q(creator=user) | Q(instructors__in=[user])
        ).distinct()

        if org_slug:
            queryset = queryset.filter(organization__slug=org_slug)
        else:
            queryset = queryset.filter(organization__isnull=True)

        if query:
            queryset = queryset.filter(title__icontains=query)

        courses = queryset.only('id', 'title', 'thumbnail')[:10]

        data = []
        for course in courses:
            data.append({
                "id": course.id,
                "title": course.title,
                "thumbnail": request.build_absolute_uri(course.thumbnail.url) if course.thumbnail else None,
            })

        return Response(data)