from datetime import timedelta
from decimal import Decimal

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.db import transaction
from django.db.models import Avg, Case, Count, DecimalField, Exists, F, OuterRef, Q, Sum, Value, When
from django.db.models.functions import Coalesce, TruncMonth
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags
from django.utils.text import slugify

from rest_framework import generics, mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from weasyprint import HTML
from django.http import HttpResponse

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions
from django.utils import timezone
from django.db.models import Q
from datetime import timedelta, datetime
from collections import defaultdict

from books.models import BookAccess, Book
from books.serializers import BookListSerializer, BookShortSerializer, DashboardBookPerformanceSerializer
from courses.models import Course, Enrollment, LessonProgress
from events.models import Event, EventRegistration
from live.models import LiveLesson
from organizations.models import Organization, OrgMembership
from revenue.models import Wallet
from .models import (
    BankingDetails,
    CreatorProfile,
    NewsletterSubscriber,
    PublisherProfile,
    StudentProfile
)

from courses.services import CourseProgressService
from payments.services.paystack_payout import create_transfer_recipient
from .permissions import IsTutor

from .serializers import (
    RegisterSerializer,
    VerifyEmailSerializer,
    LoginSerializer,
    ForgotPasswordSerializer,
    ResetPasswordSerializer,
    ChangePasswordSerializer,
    StudentProfileSerializer,
    CreatorProfileSerializer,
    DashboardLiveLessonSerializer,
    DashboardEventMinimalSerializer,
    DashboardCourseMinimalSerializer,
    CreatorProfilePublicSerializer,
    StudentProfileReadSerializer,
    NewsletterSubscriberSerializer,
    GoogleLoginSerializer,
    UserDetailSerializer,
    PublicTutorProfileSerializer,
    BankingDetailsInputSerializer,
    BankingDetailsViewSerializer,
    InstructorSearchSerializer,
    CourseAnalyticsSerializer,
    EventAnalyticsSerializer,
    PublicPublisherProfileSerializer,
    WebSocketTokenSerializer
)

User = get_user_model()
signer = TimestampSigner()

import logging
logger = logging.getLogger(__name__)


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def perform_create(self, serializer):
        try:
            user = serializer.save()

            origin = self.request.data.get('origin', settings.FRONTEND_URL).rstrip('/')

            token = signer.sign(user.email)
            verification_url = f"{origin}/verify-email/{token}/"

            html_message = render_to_string('emails/verify_email.html', {
                'user': user,
                'verification_url': verification_url
            })
            plain_message = strip_tags(html_message)

            send_mail(
                subject="Verify your account",
                message=plain_message,
                html_message=html_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False
            )
        except Exception as e:
            logger.error(f"Registration failed: {e}", exc_info=True)
            raise e

class VerifyEmailView(APIView):
    permission_classes = [permissions.AllowAny]
    def post(self, request):
        serializer = VerifyEmailSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
            user = serializer.validated_data["user"]
            user.is_active = True
            user.is_verified = True
            user.save()
            return Response({"detail": "Email verified successfully."}, status=status.HTTP_200_OK)
        except Exception:
            return Response({"detail": "Invalid or expired token."}, status=status.HTTP_400_BAD_REQUEST)


class ForgotPasswordView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]

        origin = request.data.get('origin', settings.FRONTEND_URL).rstrip('/')

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({"detail": "If email exists, a reset link will be sent."})

        token = signer.sign(user.email)
        reset_url = f"{origin}/reset-password/{token}/"

        html_message = render_to_string('emails/password_reset.html', {
            'user': user,
            'reset_url': reset_url
        })
        plain_message = strip_tags(html_message)

        send_mail(
            subject="Password reset request",
            message=plain_message,
            html_message=html_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=True
        )

        return Response({"detail": "Password reset email sent."})


class ResetPasswordView(APIView):
    permission_classes = [permissions.AllowAny]
    def post(self, request, *args, **kwargs):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token = kwargs.get("token")
        try:
            email = signer.unsign(token, max_age=60 * 60)
            user = User.objects.get(email=email)
        except (BadSignature, SignatureExpired, User.DoesNotExist):
            return Response({"detail": "Invalid or expired token."}, status=status.HTTP_400_BAD_REQUEST)
        user.set_password(serializer.validated_data["password"])
        user.save()
        return Response({"detail": "Password reset successful."}, status=status.HTTP_200_OK)

class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        if not user.check_password(serializer.validated_data["old_password"]):
            return Response({"detail": "Old password is incorrect."}, status=400)
        user.set_password(serializer.validated_data["new_password"])
        user.save()
        return Response({"detail": "Password changed successfully."})


class ResendVerificationView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get("email", "").strip().lower()
        origin = request.data.get('origin', settings.FRONTEND_URL).rstrip('/')

        success_response = Response(
            {"detail": "If an account exists with this email, a verification link has been sent."},
            status=status.HTTP_200_OK
        )

        if not email:
            return Response({"detail": "Email is required."}, status=400)

        try:
            user = User.objects.get(email=email)
            if user.is_verified:
                return success_response

            token = signer.sign(user.email)
            verification_url = f"{origin}/verify-email/{token}/"

            html_message = render_to_string('emails/verify_email.html', {
                'user': user,
                'verification_url': verification_url
            })
            plain_message = strip_tags(html_message)

            send_mail(
                subject="Verify your Evuka account",
                message=plain_message,
                html_message=html_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False
            )
            return success_response
        except User.DoesNotExist:
            return success_response
        except Exception as e:
            return Response({"detail": "An error occurred."}, status=500)


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        access_token = data["access"]
        refresh_token = data["refresh"]
        user_data = data.get("user", {})

        response = Response(
            {
                "detail": "Login successful",
                "user": user_data,
            },
            status=status.HTTP_200_OK,
        )

        secure_cookie = not settings.DEBUG

        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=secure_cookie,
            samesite="Lax",
            max_age=settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds(),
            path="/",
        )

        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=secure_cookie,
            samesite="Lax",
            max_age=settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds(),
            path="/",
        )

        return response


class GoogleLoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = GoogleLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        token = serializer.validated_data['token']

        try:
            # 1. Verify the token with Google
            # (Make sure settings.GOOGLE_CLIENT_ID matches your React .env exactly)
            idinfo = id_token.verify_oauth2_token(
                token,
                google_requests.Request(),
                settings.GOOGLE_CLIENT_ID
            )

            email = idinfo['email']
            first_name = idinfo.get('given_name', '')
            last_name = idinfo.get('family_name', '')

            # 2. Find or Create User
            try:
                user = User.objects.get(email=email)
                # Ensure verified if they logged in via Google
                if not user.is_verified:
                    user.is_verified = True
                    user.save()

            except User.DoesNotExist:
                # --- CREATE NEW USER ---
                base_username = slugify(email.split('@')[0])
                username = base_username
                counter = 1
                while User.objects.filter(username=username).exists():
                    username = f"{base_username}{counter}"
                    counter += 1

                user = User.objects.create(
                    username=username,
                    email=email,
                    first_name=first_name,
                    last_name=last_name,
                    is_verified=True,
                    is_active=True,
                    is_student=True,
                    is_tutor=False
                )

                user.set_unusable_password()
                user.save()

            # 3. Always Ensure Student Profile Exists
            StudentProfile.objects.get_or_create(user=user)

            # 4. Generate JWT
            refresh = RefreshToken.for_user(user)

            # Prepare user data
            user_data = UserDetailSerializer(user).data

            response = Response(
                {
                    "detail": "Login successful",
                    "user": user_data,
                },
                status=status.HTTP_200_OK,
            )

            # 5. Set Cookies
            secure_cookie = not settings.DEBUG

            response.set_cookie(
                key="access_token",
                value=str(refresh.access_token),
                httponly=True,
                secure=secure_cookie,
                samesite="Lax",
                max_age=settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds(),
                path="/",
            )

            response.set_cookie(
                key="refresh_token",
                value=str(refresh),
                httponly=True,
                secure=secure_cookie,
                samesite="Lax",
                max_age=settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds(),
                path="/",
            )

            return response

        except ValueError as e:
            # --- DEBUG PRINT FOR VALUE ERRORS (e.g. Audience mismatch) ---
            print(f"❌ GOOGLE AUTH VALUE ERROR: {e}")
            return Response({"detail": "Invalid Google token."}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            # --- DEBUG PRINT FOR GENERAL ERRORS ---
            print(f"❌ GENERAL LOGIN ERROR: {e}")
            return Response({"detail": "Google login failed."}, status=status.HTTP_400_BAD_REQUEST)


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        refresh_token = (request.data or {}).get("refresh") or request.COOKIES.get("refresh_token")
        response = Response({"detail": "Logged out successfully."})

        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except Exception:
                response.data = {"detail": "Invalid or expired token."}
                response.status_code = 400

        response.delete_cookie("access_token")
        response.delete_cookie("refresh_token")
        return response


class CookieTokenRefreshView(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        refresh_token = (request.data or {}).get("refresh") or request.COOKIES.get("refresh_token")
        if not refresh_token:
            return Response(
                {"detail": "Refresh token missing."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(data={"refresh": refresh_token})
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as e:
            raise InvalidToken(e.args[0])

        data = serializer.validated_data
        response = Response(data, status=status.HTTP_200_OK)

        response.set_cookie(
            key="access_token",
            value=data["access"],
            httponly=True,
            secure=not settings.DEBUG,
            samesite="Lax",
            max_age=60 * 30,
        )

        if "refresh" in data:
            response.set_cookie(
                key="refresh_token",
                value=data["refresh"],
                httponly=True,
                secure=not settings.DEBUG,
                samesite="Lax",
                max_age=60 * 60 * 24 * 7,
            )

        return response


class CurrentUserView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user

        memberships = user.memberships.filter(is_active=True).select_related('organization')

        org_data = []
        for membership in memberships:
            org = membership.organization
            org_data.append({
                "organization_name": org.name,
                "organization_slug": org.slug,
                "organization_status": org.status,
                "is_published": org.status == 'approved',
                "role": membership.role,
                "is_active": membership.is_active,
            })

        data = {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_verified": user.is_verified,
            "is_tutor": user.is_tutor,
            "is_student": user.is_student,
            "is_publisher": user.is_publisher,
            "organizations": org_data
        }

        return Response(data, status=status.HTTP_200_OK)


def calculate_course_progress(course, user):
    """
    Calculates the user's progress for a course based on completed lessons.
    This logic is run once per course to populate the progress_map.
    """
    total_lessons = course.modules.all().aggregate(
        count=Sum(Case(When(lessons__isnull=False, then=1), default=0))
    )['count'] or 0

    if total_lessons == 0:
        return 0

    completed_lessons = LessonProgress.objects.filter(
        user=user,
        is_completed=True,
        lesson__module__course=course
    ).count()

    return round((completed_lessons / total_lessons) * 100) if total_lessons > 0 else 0


class StudentDashboardAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        active_slug = request.query_params.get('active_org')
        now = timezone.now()

        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)

        active_org = None
        if active_slug:
            active_org = Organization.objects.filter(
                slug=active_slug,
                memberships__user=user,
                memberships__is_active=True
            ).first()

        context_query = Q(organization=active_org) if active_org else Q(organization__isnull=True)

        enrolled_courses = Course.objects.filter(
            enrollments__user=user,
            enrollments__status='active',
            status='published'
        ).filter(context_query).distinct()

        course_data = []
        for course in enrolled_courses:
            service = CourseProgressService(user, course)
            progress = service.calculate_progress()
            course_data.append({
                "id": course.id,
                "title": course.title,
                "slug": course.slug,
                "thumbnail": request.build_absolute_uri(course.thumbnail.url) if course.thumbnail else None,
                "progress": progress['percent'],
                "is_completed": progress['is_completed'],
                "next_lesson": self._get_next_lesson(user, course)
            })

        today_live = LiveLesson.objects.filter(
            live_class__course__in=enrolled_courses,
            start_datetime__gte=today_start,
            start_datetime__lt=today_end,
            is_cancelled=False
        ).select_related('live_class', 'live_class__course').order_by('start_datetime')

        upcoming_live = LiveLesson.objects.filter(
            live_class__course__in=enrolled_courses,
            start_datetime__gte=today_end,
            start_datetime__lte=now + timedelta(days=7),
            is_cancelled=False
        ).select_related('live_class', 'live_class__course').order_by('start_datetime')

        upcoming_events = Event.objects.filter(
            registrations__user=user,
            registrations__status='registered',
            end_time__gt=now,
            event_status__in=['approved', 'scheduled', 'ongoing']
        ).filter(course__in=enrolled_courses).order_by('start_time')[:5]

        my_books = BookAccess.objects.filter(user=user).select_related('book').order_by('-granted_at')[:4]

        my_orgs = OrgMembership.objects.filter(
            user=user, role='student', is_active=True
        ).select_related('organization')

        return Response({
            "greeting": f"Hello, {user.first_name or user.username}",
            "context": {
                "type": "organization" if active_org else "personal",
                "label": active_org.name if active_org else "Personal Workspace",
                "org_slug": active_slug
            },
            "live_today": self._serialize_live_sessions(today_live, now),
            "live_upcoming": self._serialize_live_sessions(upcoming_live, now),
            "courses": course_data,
            "events": self._serialize_events(upcoming_events, request),
            "library": self._serialize_books(my_books, request),
            "organizations": self._serialize_orgs(my_orgs, request),
        })

    def _get_next_lesson(self, user, course):
        completed_ids = user.lesson_progress.filter(
            lesson__module__course=course,
            is_completed=True
        ).values_list('lesson_id', flat=True)

        next_lesson = course.modules.prefetch_related('lessons').order_by('order').values(
            'lessons__title', 'lessons__id'
        ).exclude(lessons__id__in=completed_ids).first()

        return next_lesson['lessons__title'] if next_lesson else "Course Completed"

    def _serialize_live_sessions(self, queryset, now):
        data = []
        for session in queryset:
            is_live = session.start_datetime <= now <= session.effective_end_datetime
            can_join = is_live or (
                        now >= (session.start_datetime - timedelta(minutes=10)) and now < session.start_datetime)

            data.append({
                "id": session.id,
                "title": session.title,
                "course": session.live_class.course.title,
                "course_slug": session.live_class.course.slug,
                "start": session.start_datetime,
                "is_live": is_live,
                "can_join": can_join,
                "room_id": session.chat_room_id if can_join else None
            })
        return data

    def _serialize_events(self, queryset, request):
        return [{
            "title": e.title,
            "slug": e.slug,
            "start": e.start_time,
            "type": e.event_type,
            "banner": request.build_absolute_uri(e.banner_image.url) if e.banner_image else None
        } for e in queryset]

    def _serialize_books(self, queryset, request):
        return [{
            "title": a.book.title,
            "slug": a.book.slug,
            "cover": request.build_absolute_uri(a.book.cover_image.url) if a.book.cover_image else None,
            "author": a.book.authors
        } for a in queryset]

    def _serialize_orgs(self, queryset, request):
        return [{
            "name": m.organization.name,
            "slug": m.organization.slug,
            "logo": request.build_absolute_uri(m.organization.logo.url) if m.organization.logo else None,
            "level": m.level.name if m.level else None
        } for m in queryset]


class StudentLiveLessonsAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        now = timezone.now()

        active_slug = request.query_params.get('active_org')
        search_query = request.query_params.get('search', '')
        filter_date_str = request.query_params.get('date', None)

        active_org = None
        if active_slug:
            active_org = Organization.objects.filter(
                slug=active_slug,
                memberships__user=user,
                memberships__is_active=True
            ).first()

        context_query = Q(live_class__organization=active_org) if active_org else Q(
            live_class__organization__isnull=True)

        enrolled_course_ids = Enrollment.objects.filter(
            user=user,
            status='active'
        ).values_list('course_id', flat=True)

        lessons_qs = LiveLesson.objects.filter(
            live_class__course_id__in=enrolled_course_ids,
            is_cancelled=False
        ).filter(context_query).select_related('live_class', 'live_class__course').order_by('start_datetime')

        if search_query:
            lessons_qs = lessons_qs.filter(
                Q(title__icontains=search_query) |
                Q(live_class__course__title__icontains=search_query) |
                Q(live_class__title__icontains=search_query)
            )

        if filter_date_str:
            try:
                filter_date = datetime.strptime(filter_date_str, '%Y-%m-%d').date()
                lessons_qs = lessons_qs.filter(start_datetime__date=filter_date)
            except ValueError:
                pass

        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)

        today_sessions = []

        nested_structure = {}

        for lesson in lessons_qs:
            is_live = lesson.start_datetime <= now <= lesson.effective_end_datetime
            can_join = is_live or (
                        now >= (lesson.start_datetime - timedelta(minutes=10)) and now < lesson.start_datetime)

            lesson_data = {
                "id": lesson.id,
                "title": lesson.title,
                "course_title": lesson.live_class.course.title,
                "course_slug": lesson.live_class.course.slug,
                "start": lesson.start_datetime,
                "end": lesson.end_datetime,
                "is_live": is_live,
                "can_join": can_join,
                "status": lesson.status
            }

            if today_start <= lesson.start_datetime < today_end:
                today_sessions.append(lesson_data)

            c_title = lesson.live_class.course.title
            lc_title = lesson.live_class.title

            if c_title not in nested_structure:
                nested_structure[c_title] = {}

            if lc_title not in nested_structure[c_title]:
                nested_structure[c_title][lc_title] = []

            nested_structure[c_title][lc_title].append(lesson_data)

        grouped_data = []
        for c_name, classes in nested_structure.items():
            class_list = []
            for lc_name, lessons in classes.items():
                class_list.append({"class_title": lc_name, "lessons": lessons})
            grouped_data.append({"course": c_name, "classes": class_list})

        return Response({
            "context": {
                "type": "organization" if active_org else "personal",
                "label": active_org.name if active_org else "Personal Workspace",
            },
            "happening_today": today_sessions,
            "grouped_data": grouped_data,
            "meta": {
                "total_count": lessons_qs.count(),
                "filter_date": filter_date_str
            }
        })


class StudentProfileManageView(generics.RetrieveUpdateAPIView, generics.CreateAPIView):
    """
    A single view for a user to manage their StudentProfile.
    """
    serializer_class = StudentProfileSerializer
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        """Use the ReadSerializer for GET requests, and the WriteSerializer otherwise."""
        if self.request.method == 'GET':
            return StudentProfileReadSerializer
        return StudentProfileSerializer

    def get_queryset(self):
        return StudentProfile.objects.filter(user=self.request.user).annotate(
            enrolled_courses_count=Count('user__enrollments', filter=Q(user__enrollments__status='active')),
            completed_courses_count=Count('user__enrollments', filter=Q(user__enrollments__status='completed')),
            certificates_count=Count('user__certificates')
        ).prefetch_related('user__certificates', 'user__memberships')

    def get_object(self):
        """
        Returns the single profile for the logged-in user.
        """
        obj = get_object_or_404(self.get_queryset())
        return obj

    def create(self, request, *args, **kwargs):
        """
        Override 'create' to check for an existing student profile.
        """
        if hasattr(request.user, 'marketplace_learner'):
            return Response(
                {"error": "You already have a student profile."},
                status=status.HTTP_400_BAD_REQUEST
            )
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        """
        Hook to set the user and update the user's role flag.
        """
        serializer.save(user=self.request.user)

        user = self.request.user
        if not user.is_student:
            user.is_student = True
            user.save(update_fields=['is_student'])


class CreatorProfileManageView(generics.RetrieveUpdateAPIView, generics.CreateAPIView):
    """
    A single view for a user to manage their CreatorProfile.
    - POST: Onboards a new tutor. Creates the profile and sets 'is_tutor=True'.
    - GET: Retrieves the user's existing tutor profile.
    - PUT/PATCH: Updates the user's existing tutor profile.
    """
    serializer_class = CreatorProfileSerializer
    parser_classes = [MultiPartParser, FormParser]

    def get_permissions(self):
        if self.request.method == 'POST':
            self.permission_classes = [permissions.IsAuthenticated]
        else:
            self.permission_classes = [permissions.IsAuthenticated, IsTutor]
        return super().get_permissions()

    def get_queryset(self):
        return CreatorProfile.objects.filter(user=self.request.user)

    def get_object(self):
        obj = generics.get_object_or_404(self.get_queryset())
        return obj

    def create(self, request, *args, **kwargs):
        if hasattr(request.user, 'creator_profile'):
            return Response(
                {"error": "You already have a creator profile."},
                status=status.HTTP_400_BAD_REQUEST
            )
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
        user = self.request.user
        if not user.is_tutor:
            user.is_tutor = True
            user.save(update_fields=['is_tutor'])


class TutorDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        active_org = getattr(request, "active_organization", None)
        now = timezone.now()

        COMMISSION_RATE = Decimal('0.10')
        NET_PERCENTAGE = Decimal('1.00') - COMMISSION_RATE

        if active_org:
            membership = OrgMembership.objects.filter(user=user, organization=active_org, is_active=True).first()
            if not membership:
                return Response({"error": "Unauthorized context"}, status=403)

            is_admin = membership.role in ["admin", "owner"]

            if is_admin:
                wallet, _ = Wallet.objects.get_or_create(owner_org=active_org)
                courses_qs = Course.objects.filter(organization=active_org)
                events_qs = Event.objects.filter(course__organization=active_org)
                memberships_qs = OrgMembership.objects.filter(organization=active_org, payment_status='paid')
            else:
                wallet, _ = Wallet.objects.get_or_create(owner_user=user)
                courses_qs = Course.objects.filter(organization=active_org, creator=user)
                events_qs = Event.objects.filter(organizer=user)
                memberships_qs = OrgMembership.objects.none()
        else:
            wallet, _ = Wallet.objects.get_or_create(owner_user=user)
            courses_qs = Course.objects.filter(organization__isnull=True, creator=user)
            events_qs = Event.objects.filter(organizer=user)
            memberships_qs = OrgMembership.objects.none()

        metrics = self._calculate_complex_metrics(
            courses_qs,
            events_qs,
            memberships_qs,
            active_org,
            now,
            wallet,
            NET_PERCENTAGE
        )

        best_courses = courses_qs.annotate(
            student_count=Count('enrollments', filter=Q(enrollments__status='active')),
            revenue=Coalesce(
                Sum(
                    Coalesce(F('enrollments__course__price'), Value(0)) * NET_PERCENTAGE,
                    filter=Q(enrollments__status='active'),
                    output_field=DecimalField()
                ),
                Decimal('0')
            )
        ).order_by('-student_count')[:5]

        best_events = events_qs.annotate(
            attendee_count=Count('registrations', filter=Q(registrations__status='registered')),
            revenue=Coalesce(
                Sum(
                    Coalesce(F('price'), Value(0)) * NET_PERCENTAGE,
                    filter=Q(registrations__payment_status='paid'),
                    output_field=DecimalField()
                ),
                Decimal('0')
            )
        ).order_by('-attendee_count')[:5]

        upcoming_classes = LiveLesson.objects.filter(
            live_class__course__in=courses_qs,
            is_cancelled=False,
            end_datetime__gte=now
        ).select_related('live_class', 'live_class__course').order_by('start_datetime')[:5]

        return Response({
            "metrics": metrics,
            "upcoming_classes": DashboardLiveLessonSerializer(upcoming_classes, many=True, context={'request': request}).data,
            "best_performing_courses": DashboardCourseMinimalSerializer(best_courses, many=True, context={'request': request}).data,
            "best_performing_events": DashboardEventMinimalSerializer(best_events, many=True, context={'request': request}).data,
        })

    def _calculate_complex_metrics(self, courses_qs, events_qs, memberships_qs, active_org, now, wallet, net_pct):
        course_revenue = Enrollment.objects.filter(
            course__in=courses_qs,
            status='active'
        ).aggregate(
            total=Sum(
                Coalesce(F('course__price'), Value(0)) * net_pct,
                output_field=DecimalField()
            )
        )['total'] or Decimal('0')

        event_revenue = EventRegistration.objects.filter(
            event__in=events_qs,
            payment_status='paid'
        ).aggregate(
            total=Sum(
                Coalesce(F('event__price'), Value(0)) * net_pct,
                output_field=DecimalField()
            )
        )['total'] or Decimal('0')

        sub_revenue = memberships_qs.aggregate(
            total=Sum(
                Coalesce(F('organization__membership_price'), Value(0)) * net_pct,
                output_field=DecimalField()
            )
        )['total'] or Decimal('0')

        active_students = Enrollment.objects.filter(course__in=courses_qs, status='active').values('user').distinct().count()

        return {
            "total_courses": courses_qs.count(),
            "active_students": active_students,
            "available_balance": float(wallet.balance),
            "net_lifetime_revenue": float(course_revenue + event_revenue + sub_revenue),
            "revenue_breakdown": {
                "courses": float(course_revenue),
                "events": float(event_revenue),
                "subscriptions": float(sub_revenue) if sub_revenue > 0 else 0
            },
            "upcoming_events": events_qs.filter(end_time__gte=now).count(),
        }


class TutorAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        course_id = request.query_params.get('course_id')
        active_org = getattr(request, "active_organization", None)

        if course_id:
            return self._get_course_specific_analytics(user, course_id)

        return self._get_general_dashboard_analytics(user, active_org)

    def _get_general_dashboard_analytics(self, user, active_org):
        if active_org:
            courses = Course.objects.filter(organization=active_org)
            enrollment_qs = Enrollment.objects.filter(course__organization=active_org)
            events = Event.objects.filter(course__organization=active_org)
        else:
            courses = Course.objects.filter(organization__isnull=True, creator=user)
            enrollment_qs = Enrollment.objects.filter(course__creator=user)
            events = Event.objects.filter(organizer=user)

        six_months_ago = timezone.now() - timedelta(days=180)
        trends = enrollment_qs.filter(date_joined__gte=six_months_ago) \
            .annotate(month=TruncMonth('date_joined')) \
            .values('month') \
            .annotate(
                enrollments=Count('id'),
                revenue=Sum('course__price')
            ).order_by('month')

        course_data = CourseAnalyticsSerializer(courses, many=True).data
        event_data = EventAnalyticsSerializer(events[:5], many=True).data

        total_course_rev = sum(c['revenue_metrics']['total'] for c in course_data)
        total_event_rev = sum(e['registration_stats']['revenue'] for e in event_data)

        return Response({
            "kpis": {
                "total_revenue": total_course_rev + total_event_rev,
                "total_enrollments": sum(c['student_metrics']['total'] for c in course_data),
                "active_events": events.filter(event_status='approved').count(),
                "avg_rating": courses.aggregate(Avg('rating_avg'))['rating_avg__avg'] or 0
            },
            "trends": list(trends),
            "course_breakdown": course_data,
            "upcoming_events": event_data
        })

    def _get_course_specific_analytics(self, user, course_id):
        course = Course.objects.filter(Q(creator=user) | Q(instructors__in=[user]), id=course_id).first()

        if not course:
            return Response({"error": "Course not found or access denied"}, status=status.HTTP_404_NOT_FOUND)

        events = course.events.all().order_by('-start_time')

        enrollment_trend = Enrollment.objects.filter(course=course) \
            .annotate(month=TruncMonth('date_joined')) \
            .values('month') \
            .annotate(
                enrollments=Count('id'),
                revenue=Sum('course__price')
            ).order_by('month')

        return Response({
            "course_info": CourseAnalyticsSerializer(course).data,
            "trends": list(enrollment_trend),
            "related_events": EventAnalyticsSerializer(events, many=True).data
        })


class ExportTutorPDFView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        now = timezone.now()
        active_org = getattr(request, "active_organization", None)

        if active_org:
            courses_base = Course.objects.filter(organization=active_org)
            enrollment_qs = Enrollment.objects.filter(course__organization=active_org)
            events_qs = Event.objects.filter(course__organization=active_org)
        else:
            courses_base = Course.objects.filter(organization__isnull=True, creator=user)
            enrollment_qs = Enrollment.objects.filter(course__creator=user)
            events_qs = Event.objects.filter(organizer=user)

        total_course_revenue = enrollment_qs.aggregate(
            total=Sum(Coalesce(F('course__price'), Value(0), output_field=DecimalField()))
        )['total'] or Decimal('0')

        total_event_revenue = events_qs.aggregate(
            total=Sum(Coalesce(F('price'), Value(0), output_field=DecimalField()))
        )['total'] or Decimal('0')

        metrics = {
            "total_revenue": float(total_course_revenue + total_event_revenue),
            "total_enrollments": enrollment_qs.count(),
            "active_courses": courses_base.filter(status='published').count(),
            "avg_rating": courses_base.aggregate(Avg('rating_avg'))['rating_avg__avg'] or 0,
            "total_events": events_qs.count()
        }

        course_performance = courses_base.annotate(
            student_count=Count('enrollments', distinct=True),
            revenue=Coalesce(
                Sum(F('enrollments__course__price'), output_field=DecimalField()),
                Value(0, output_field=DecimalField())
            )
        ).order_by('-student_count')

        context = {
            'tutor': user.get_full_name() or user.username,
            'organization': active_org.name if active_org else "Personal Account",
            'metrics': metrics,
            'courses': course_performance,
            'events': events_qs.filter(start_time__gte=now).order_by('start_time')[:10],
            'date': now.strftime("%B %d, %Y"),
        }

        html_string = render_to_string('pdf/tutor_report.html', context)
        html = HTML(string=html_string, base_url=request.build_absolute_uri())
        pdf_file = html.write_pdf()

        response = HttpResponse(pdf_file, content_type='application/pdf')
        filename = f"Tutor_Report_{now.strftime('%Y%m%d')}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        return response


class PublicTutorViewSet(mixins.RetrieveModelMixin,
                         mixins.ListModelMixin,
                         viewsets.GenericViewSet):
    """
    Publicly lists and retrieves verified tutor profiles.
    - /users/api/tutors/ -> Lists all verified tutors.
    - /users/api/tutors/[username]/ -> Retrieves a specific tutor's profile.
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = CreatorProfilePublicSerializer
    lookup_field = 'user__username'
    lookup_url_kwarg = 'username'

    def get_queryset(self):
        return CreatorProfile.objects.filter(
            is_verified=True,
            user__is_tutor=True
        ).select_related('user').prefetch_related('subjects')


class GetWebSocketTokenView(APIView):
    """
    Provides a JWT token via the response body for the client to use
    in the WebSocket URL query string, bypassing HTTP cookie isolation.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        token = str(AccessToken.for_user(request.user))

        serializer = WebSocketTokenSerializer({'token': token})
        return Response(serializer.data)


class NewsletterSubscribeView(generics.CreateAPIView):
    queryset = NewsletterSubscriber.objects.all()
    serializer_class = NewsletterSubscriberSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        email = request.data.get('email', '').strip().lower()

        if not email:
            return Response({"email": "This field is required."}, status=status.HTTP_400_BAD_REQUEST)

        subscriber = NewsletterSubscriber.objects.filter(email=email).first()

        if subscriber:
            if subscriber.is_active:
                return Response(
                    {"message": "You are already subscribed!"},
                    status=status.HTTP_200_OK
                )
            else:
                subscriber.is_active = True
                subscriber.save()
                self._send_welcome_email(email)
                return Response(
                    {"message": "Welcome back! You have been resubscribed."},
                    status=status.HTTP_200_OK
                )

        linked_user = User.objects.filter(email=email).first()

        NewsletterSubscriber.objects.create(
            email=email,
            user=linked_user
        )

        self._send_welcome_email(email)

        return Response(
            {"message": "Successfully subscribed to the newsletter!"},
            status=status.HTTP_201_CREATED
        )

    def _send_welcome_email(self, email):
        origin = self.request.data.get('origin', settings.FRONTEND_URL).rstrip('/')

        token = signer.sign(email)
        unsubscribe_url = f"{origin}/newsletter/unsubscribe/{token}"

        html_message = render_to_string('emails/newsletter_welcome.html', {
            'unsubscribe_url': unsubscribe_url
        })
        plain_message = strip_tags(html_message)

        send_mail(
            subject="Welcome to e-vuka!",
            message=plain_message,
            html_message=html_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=True
        )


class NewsletterUnsubscribeView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, token):
        try:
            email = signer.unsign(token, max_age=60 * 60 * 24 * 3)

            subscriber = NewsletterSubscriber.objects.filter(email=email).first()
            if subscriber:
                subscriber.delete()  # Or set subscriber.is_active = False
                return Response({"detail": "You have been successfully unsubscribed."}, status=status.HTTP_200_OK)
            else:
                return Response({"detail": "Subscriber not found."}, status=status.HTTP_404_NOT_FOUND)

        except (BadSignature, SignatureExpired):
            return Response({"detail": "Invalid or expired link."}, status=status.HTTP_400_BAD_REQUEST)


class PublicTutorProfileView(generics.RetrieveAPIView):
    """
    Public endpoint to retrieve a tutor's profile details by their username.
    Endpoint: GET /users/tutor/<username>/
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = PublicTutorProfileSerializer
    lookup_field = 'user__username'
    lookup_url_kwarg = 'username'

    def get_queryset(self):
        return CreatorProfile.objects.select_related('user').prefetch_related(
            'subjects',
            'courses__global_subcategory',
            'courses__global_level'
        )

    def get_object(self):
        """
        Override get_object to handle the lookup by username
        on the related User model.
        """
        queryset = self.filter_queryset(self.get_queryset())
        username = self.kwargs.get(self.lookup_url_kwarg)

        # Ensure we are looking up by the related User's username
        obj = get_object_or_404(queryset, user__username=username)

        self.check_object_permissions(self.request, obj)
        return obj


class PublicPublisherProfileView(generics.RetrieveAPIView):
    """
    Public endpoint to retrieve a publisher's profile details by their username.
    Endpoint: GET /users/publisher/<username>/
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = PublicPublisherProfileSerializer
    lookup_field = 'user__username'
    lookup_url_kwarg = 'username'

    def get_queryset(self):
        return PublisherProfile.objects.select_related('user').prefetch_related(
            'books__categories'
        )

    def get_object(self):
        queryset = self.filter_queryset(self.get_queryset())
        username = self.kwargs.get(self.lookup_url_kwarg)

        obj = get_object_or_404(queryset, user__username=username)

        self.check_object_permissions(self.request, obj)
        return obj


class PayoutMethodView(APIView):
    """
    Manage Payout Methods (Bank/MPESA).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Show current linked account"""
        if hasattr(request.user, 'banking_details'):
            serializer = BankingDetailsViewSerializer(request.user.banking_details)
            return Response(serializer.data)
        return Response({"message": "No payout method linked"}, status=200)

    def post(self, request):
        """
        Add/Update Payout Method.
        Steps:
        1. Validate Input
        2. Send to Paystack -> Get Recipient Code
        3. Save Recipient Code to DB
        """
        serializer = BankingDetailsInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        data = serializer.validated_data

        try:
            # 1. Talk to Paystack (Tokenize the sensitive data)
            # This function calls Paystack API
            recipient_data = create_transfer_recipient(
                name=data['account_name'],
                account_number=data['account_number'],
                bank_code=data['bank_code']
            )

            # 2. Extract safe data
            code = recipient_data['recipient_code']
            # Paystack returns the official bank name (e.g. "KCB Bank")
            bank_name_confirmed = recipient_data.get('details', {}).get('bank_name', data['bank_code'])

            # 3. Create Masked Number (e.g., 0712***89)
            raw_num = data['account_number']
            if len(raw_num) > 4:
                masked = f"{raw_num[:3]}****{raw_num[-2:]}"
            else:
                masked = "****"

            # 4. Save to DB (Update if exists)
            BankingDetails.objects.update_or_create(
                user=request.user,
                defaults={
                    "paystack_recipient_code": code,
                    "bank_name": bank_name_confirmed,
                    "display_number": masked,
                    "is_verified": True
                }
            )

            return Response({
                "message": "Payout method linked successfully!",
                "bank": bank_name_confirmed
            }, status=201)

        except Exception as e:
            return Response({"error": str(e)}, status=400)


class SearchInstructorsView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = InstructorSearchSerializer

    def get_queryset(self):
        query = self.request.query_params.get('q', '').strip()
        org_slug = self.request.query_params.get('org_slug', None)  # Get org context

        base_filters = Q(creator_profile__isnull=False)

        if org_slug:
            org_filters = Q(
                memberships__organization__slug=org_slug,
                memberships__is_active=True,
                memberships__role__in=['tutor', 'admin', 'owner']
            )
            base_filters &= org_filters

        if len(query) >= 3:
            text_filters = Q(username__icontains=query) | Q(creator_profile__display_name__icontains=query)
            base_filters &= text_filters
        elif not org_slug:
            return User.objects.none()

        qs = User.objects.filter(base_filters).select_related('creator_profile').distinct()

        return qs[:10]


class PublisherDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        now = timezone.now()

        COMMISSION_RATE = Decimal('0.10')
        NET_PERCENTAGE = Decimal('1.00') - COMMISSION_RATE

        wallet, _ = Wallet.objects.get_or_create(owner_user=user)
        books_qs = Book.objects.filter(created_by=user)

        metrics = self._calculate_book_metrics(books_qs, wallet, NET_PERCENTAGE)

        best_books = books_qs.annotate(
            actual_sales=Count('readers'),
            revenue=Coalesce(
                Sum(
                    Coalesce(F('price'), Value(0)) * NET_PERCENTAGE,
                    output_field=DecimalField()
                ),
                Decimal('0')
            )
        ).order_by('-actual_sales')[:5]

        recent_drafts = books_qs.filter(status='draft').order_by('-updated_at')[:5]

        return Response({
            "metrics": metrics,
            "best_performing_books": DashboardBookPerformanceSerializer(
                best_books,
                many=True,
                context={'request': request}
            ).data,
            "recent_drafts": BookShortSerializer(
                recent_drafts,
                many=True
            ).data
        })

    def _calculate_book_metrics(self, books_qs, wallet, net_pct):
        book_revenue = BookAccess.objects.filter(
            book__in=books_qs
        ).aggregate(
            total=Sum(
                Coalesce(F('book__price'), Value(0)) * net_pct,
                output_field=DecimalField()
            )
        )['total'] or Decimal('0')

        total_readers = BookAccess.objects.filter(book__in=books_qs).values('user').distinct().count()
        total_views = books_qs.aggregate(total=Sum('view_count'))['total'] or 0

        return {
            "total_books": books_qs.count(),
            "published_count": books_qs.filter(status='published').count(),
            "total_readers": total_readers,
            "total_views": total_views,
            "available_balance": float(wallet.balance),
            "net_book_revenue": float(book_revenue),
        }



