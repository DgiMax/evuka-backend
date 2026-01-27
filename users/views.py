from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404
from django.utils.text import slugify
from django.db.models.functions import TruncMonth
from django.conf import settings
from rest_framework import generics, status, permissions
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework import viewsets, mixins, permissions
from rest_framework.decorators import action
from django.db.models import Count, Sum, Q, Case, When, DecimalField, Avg
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from datetime import timedelta

from courses.models import Course, Enrollment, LessonProgress
from events.models import Event
from live.models import LiveLesson
from organizations.models import OrgMembership, Organization
from payments.services.paystack_payout import create_transfer_recipient
from revenue.models import Payout, Transaction, Wallet
from .models import CreatorProfile, StudentProfile, NewsletterSubscriber, BankingDetails
from .permissions import IsTutor
from .serializers import (
    RegisterSerializer,
    VerifyEmailSerializer,
    LoginSerializer,
    ForgotPasswordSerializer,
    StudentDashboardOrgSerializer,
    ResetPasswordSerializer,
    ChangePasswordSerializer, DashboardEventSerializer, DashboardCourseSerializer,
    StudentProfileSerializer,
    CreatorProfileSerializer, DashboardLiveLessonSerializer, DashboardEventMinimalSerializer,
    DashboardCourseMinimalSerializer, WalletSerializer, TransactionSerializer,
    PayoutSerializer, CreatorProfilePublicSerializer, StudentProfileReadSerializer, NewsletterSubscriberSerializer,
    GoogleLoginSerializer, UserDetailSerializer, PublicTutorProfileSerializer, BankingDetailsInputSerializer,
    BankingDetailsViewSerializer, InstructorSearchSerializer, CourseAnalyticsSerializer, EventAnalyticsSerializer,
)
from users.serializers import WebSocketTokenSerializer

User = get_user_model()
signer = TimestampSigner()

import logging
logger = logging.getLogger(__name__)

class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def perform_create(self, serializer):
        try:
            logger.info("Starting user registration...")
            print("DEBUG: Starting user registration...")

            # Save user
            user = serializer.save()
            logger.info(f"User saved: {user}")
            print(f"DEBUG: User saved: {user}")

            # Generate token and verification URL
            token = signer.sign(user.email)
            verification_url = f"{settings.FRONTEND_URL}/verify-email/{token}/"
            logger.info(f"Verification URL: {verification_url}")
            print(f"DEBUG: Verification URL: {verification_url}")

            # Render email
            html_message = render_to_string('emails/verify_email.html', {
                'user': user,
                'verification_url': verification_url
            })
            plain_message = strip_tags(html_message)
            logger.info("Email rendered successfully")
            print("DEBUG: Email rendered successfully")

            # Send email
            send_mail(
                subject="Verify your account",
                message=plain_message,
                html_message=html_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False  # Change to False to catch email errors
            )
            logger.info("Email sent successfully")
            print("DEBUG: Email sent successfully")

        except Exception as e:
            logger.error(f"Registration failed: {e}", exc_info=True)
            print(f"DEBUG: Registration failed: {e}")
            raise e  # re-raise so DRF returns the error

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

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({"detail": "If email exists, a reset link will be sent."})

        token = signer.sign(user.email)
        reset_url = f"{settings.FRONTEND_URL}/reset-password/{token}/"

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
        email = request.data.get("email")
        try:
            user = User.objects.get(email=email)
            if user.is_verified:
                return Response({"detail": "User already verified."}, status=400)

            token = signer.sign(user.email)
            verification_url = f"{settings.FRONTEND_URL}/verify-email/{token}/"

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
                fail_silently=True
            )
            return Response({"detail": "Verification email sent."})
        except User.DoesNotExist:
            return Response({"detail": "User not found."}, status=400)


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
            org_data.append({
                "organization_name": membership.organization.name,
                "organization_slug": membership.organization.slug,
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


class DashboardAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        active_slug = request.query_params.get('active_org')
        now = timezone.now()

        active_org = None
        org_level_id = None
        display_name = user.get_full_name() or user.username
        context_type = "personal"

        # 1. Determine Context (Personal vs Organization)
        try:
            if active_slug:
                active_org = Organization.objects.get(slug=active_slug)
                membership = OrgMembership.objects.get(
                    user=user,
                    organization=active_org,
                    is_active=True
                )
                org_level_id = membership.level_id
                display_name = active_org.name
                context_type = "organization"
        except (Organization.DoesNotExist, OrgMembership.DoesNotExist):
            active_org = None
            org_level_id = None

        # 2. Base Course Query
        course_qs = Course.objects.filter(
            enrollments__user=user,
            enrollments__status='active',
            status='published'
        ).select_related('organization', 'org_level', 'creator').prefetch_related('modules__lessons')

        # Apply Context Filters
        if context_type == "organization":
            course_qs = course_qs.filter(organization=active_org)
            if org_level_id:
                course_qs = course_qs.filter(org_level_id=org_level_id)
        else:
            course_qs = course_qs.filter(organization__isnull=True)

        # 3. ADVANCED PROGRESS CALCULATION (Annotations)
        # This replaces the slow loop with a single efficient database query
        enrolled_courses = course_qs.annotate(
            # --- Denominator (Totals) ---
            total_lessons=Count('modules__lessons', distinct=True),
            total_assignments=Count('modules__assignments', distinct=True),
            total_quizzes=Count('modules__lessons__quizzes', distinct=True),

            # --- Numerator (Completed) ---
            completed_lessons=Count(
                'modules__lessons__progress_records',
                filter=Q(
                    modules__lessons__progress_records__user=user,
                    modules__lessons__progress_records__is_completed=True
                ),
                distinct=True
            ),
            completed_assignments=Count(
                'modules__assignments__submissions',
                filter=Q(modules__assignments__submissions__user=user),
                distinct=True
            ),
            completed_quizzes=Count(
                'modules__lessons__quizzes__attempts',
                filter=Q(
                    modules__lessons__quizzes__attempts__user=user,
                    modules__lessons__quizzes__attempts__is_completed=True
                ),
                distinct=True
            )
        )

        # 4. Calculate Percentage in Python (Fast in-memory math)
        progress_map = {}
        for course in enrolled_courses:
            # Weighted total matches your CourseProgressService logic
            weighted_total = course.total_lessons + course.total_assignments + course.total_quizzes
            weighted_completed = course.completed_lessons + course.completed_assignments + course.completed_quizzes

            if weighted_total > 0:
                percent = round((weighted_completed / weighted_total) * 100)
                percent = min(percent, 100)  # Cap at 100%
            else:
                percent = 0

            progress_map[course.id] = percent

        # 5. Fetch Events
        event_qs = Event.objects.filter(
            registrations__user=user,
            registrations__status='registered',
            start_time__gte=now,
            event_status__in=['approved', 'scheduled']
        ).select_related('course')

        if context_type == "organization":
            event_qs = event_qs.filter(course__organization=active_org)
        else:
            event_qs = event_qs.filter(course__organization__isnull=True)

        registered_events = list(event_qs.order_by('start_time')[:6])

        # 6. Fetch Student Organizations (New feature for Personal Dashboard)
        student_organizations = []
        if context_type == "personal":
            # Only fetch orgs where the user is a STUDENT
            org_memberships = OrgMembership.objects.filter(
                user=user,
                role='student',
                is_active=True
            ).select_related('organization', 'level')

            # Use the new serializer we created
            student_organizations = StudentDashboardOrgSerializer(
                org_memberships,
                many=True,
                context={'request': request}
            ).data

        # 7. Serialize Data
        course_serializer = DashboardCourseSerializer(
            enrolled_courses,
            many=True,
            context={'request': request, 'progress_map': progress_map}
        )

        event_serializer = DashboardEventSerializer(
            registered_events,
            many=True,
            context={'request': request}
        )

        data = {
            'context_type': context_type,
            'display_name': display_name,
            'enrolled_courses': course_serializer.data,
            'registered_events': event_serializer.data,
            'my_organizations': student_organizations,  # Added here
        }

        return Response(data, status=status.HTTP_200_OK)


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
        """Returns the logged-in user's StudentProfile."""
        return StudentProfile.objects.filter(user=self.request.user)

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

        if active_org:
            membership = OrgMembership.objects.filter(user=user, organization=active_org).first()
            if not membership:
                return Response({"error": "Unauthorized context"}, status=status.HTTP_403_FORBIDDEN)

            is_admin = membership.role in ["admin", "owner"]
            if is_admin:
                courses_qs = Course.objects.filter(organization=active_org)
                events_qs = Event.objects.filter(course__organization=active_org)
            else:
                courses_qs = Course.objects.filter(organization=active_org, creator=user)
                events_qs = Event.objects.filter(course__organization=active_org, organizer=user)
        else:
            courses_qs = Course.objects.filter(organization__isnull=True, creator=user)
            events_qs = Event.objects.filter(course__organization__isnull=True, organizer=user)

        metrics = self._calculate_metrics(courses_qs, events_qs, active_org, now)

        upcoming_classes = LiveLesson.objects.filter(
            live_class__course__in=courses_qs,
            is_cancelled=False,
            end_datetime__gte=now
        ).select_related('live_class', 'live_class__course').order_by('start_datetime')[:5]

        upcoming_events = events_qs.filter(
            start_time__gte=now,
            event_status="approved"
        ).order_by('start_time')[:5]

        best_courses = courses_qs.annotate(
            student_count=Count('enrollments', filter=Q(enrollments__status='active')),
            revenue=Coalesce(
                Sum('enrollments__course__price', filter=Q(enrollments__status='active')),
                0,
                output_field=DecimalField()
            )
        ).order_by('-student_count')[:5]

        return Response({
            "metrics": metrics,
            "upcoming_classes": DashboardLiveLessonSerializer(upcoming_classes, many=True, context={'request': request}).data,
            "upcoming_events": DashboardEventMinimalSerializer(upcoming_events, many=True, context={'request': request}).data,
            "best_performing_courses": DashboardCourseMinimalSerializer(best_courses, many=True, context={'request': request}).data,
        })

    def _calculate_metrics(self, courses_qs, events_qs, active_org, now):
        total_students = Enrollment.objects.filter(
            course__in=courses_qs,
            status='active'
        ).values('user').distinct().count()

        revenue_total = Enrollment.objects.filter(
            course__in=courses_qs,
            status='active'
        ).aggregate(
            total=Coalesce(Sum('course__price'), 0, output_field=DecimalField())
        )['total']

        active_tutors = 1
        if active_org:
            active_tutors = OrgMembership.objects.filter(
                organization=active_org,
                role__in=['tutor', 'admin', 'owner'],
                is_active=True
            ).count()

        return {
            "total_courses": courses_qs.count(),
            "active_students": total_students,
            "total_revenue": float(revenue_total),
            "upcoming_events": events_qs.filter(start_time__gte=now).count(),
            "active_tutors": active_tutors
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
        token = signer.sign(email)
        unsubscribe_url = f"{settings.FRONTEND_URL}/newsletter/unsubscribe/{token}"

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