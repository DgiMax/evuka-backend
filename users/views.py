from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404
from django.utils.text import slugify
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
from django.db.models import Count, Sum, Q, Case, When, DecimalField
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from courses.models import Course, Enrollment, LessonProgress
from events.models import Event
from live.models import LiveLesson
from organizations.models import OrgMembership, Organization
from revenue.models import Payout, Transaction, Wallet
from .models import CreatorProfile, StudentProfile, TutorPayoutMethod, NewsletterSubscriber
from .permissions import IsTutor
from .serializers import (
    RegisterSerializer,
    VerifyEmailSerializer,
    LoginSerializer,
    ForgotPasswordSerializer,
    ResetPasswordSerializer,
    ChangePasswordSerializer, DashboardEventSerializer, DashboardCourseSerializer,
    StudentProfileSerializer,
    CreatorProfileSerializer, DashboardLiveLessonSerializer, DashboardEventMinimalSerializer,
    DashboardCourseMinimalSerializer, WalletSerializer, TransactionSerializer, TutorPayoutMethodSerializer,
    PayoutSerializer, CreatorProfilePublicSerializer, StudentProfileReadSerializer, NewsletterSubscriberSerializer,
    GoogleLoginSerializer, UserDetailSerializer,
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
                    is_verified=True,  # Trusted provider
                    is_active=True,
                    is_student=True,  # ✅ Default Role
                    is_tutor=False  # ✅ Tutor logic handles update later
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
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user

        active_slug = request.query_params.get('active_org')
        now = timezone.now()

        active_org = None
        org_level_id = None
        display_name = user.get_full_name() or user.username
        context_type = "personal"

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

        course_qs = Course.objects.filter(
            enrollments__user=user,
            enrollments__status='active',
            status='published'
        ).select_related('organization', 'org_level', 'creator').prefetch_related('modules__lessons')

        if context_type == "organization":
            course_qs = course_qs.filter(organization=active_org)

            if org_level_id:
                course_qs = course_qs.filter(
                    org_level_id=org_level_id
                )
            else:
                pass

        else:
            course_qs = course_qs.filter(organization__isnull=True)

        enrolled_courses = list(course_qs)

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

        progress_map = {
            course.id: calculate_course_progress(course, user)
            for course in enrolled_courses
        }

        course_serializer = DashboardCourseSerializer(
            enrolled_courses,
            many=True,
            context={'request': request, 'progress_map': progress_map}
        )

        event_serializer = DashboardEventSerializer(registered_events, many=True, context={'request': request})

        data = {
            'context_type': context_type,
            'display_name': display_name,
            'enrolled_courses': course_serializer.data,
            'registered_events': event_serializer.data,
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
    """
    Context-aware dashboard for Tutors and Org Admins.
    Returns metrics and lists based on the active organization (or lack thereof).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, format=None):
        user = request.user
        active_org = getattr(request, "active_organization", None)
        today = timezone.now().date()
        now = timezone.now()

        if active_org:
            membership = OrgMembership.objects.filter(user=user, organization=active_org).first()
            if not membership:
                 return Response({"error": "Not a member of this organization"}, status=status.HTTP_403_FORBIDDEN)

            is_admin = membership.role in ["admin", "owner"]

            if is_admin:
                courses_qs = Course.objects.filter(organization=active_org)
                events_qs = Event.objects.filter(course__organization=active_org)
                context_label = "Organization Admin View"
            else:
                courses_qs = Course.objects.filter(organization=active_org, creator=user)
                events_qs = Event.objects.filter(course__organization=active_org, organizer=user)
                context_label = "Organization Tutor View"
        else:
            courses_qs = Course.objects.filter(organization__isnull=True, creator=user)
            events_qs = Event.objects.filter(course__organization__isnull=True, organizer=user)
            context_label = "Personal Tutor View"

        total_courses = courses_qs.count()
        total_events = events_qs.count()
        upcoming_events_count = events_qs.filter(start_time__gte=now).count()

        total_students = Enrollment.objects.filter(
            course__in=courses_qs,
            status='active'
        ).values('user').distinct().count()

        active_tutors_count = 0
        if active_org and is_admin:
             active_tutors_count = OrgMembership.objects.filter(
                 organization=active_org,
                 role__in=['tutor', 'admin', 'owner'],
                 is_active=True
             ).count()
        elif active_org or not active_org:
             active_tutors_count = 1

        revenue_agg = Enrollment.objects.filter(
            course__in=courses_qs,
            status='active'
         ).aggregate(
            total=Coalesce(Sum('course__price'), 0, output_field=DecimalField())
        )
        total_revenue = revenue_agg['total']

        upcoming_classes_qs = LiveLesson.objects.filter(
            live_class__course__in=courses_qs,
            date__gte=today,
        ).select_related('live_class', 'live_class__course').order_by('date', 'start_time')[:5]

        upcoming_events_list_qs = events_qs.filter(
            start_time__gte=now
        ).order_by('start_time')[:5]

        best_courses_qs = courses_qs.annotate(
            student_count=Count('enrollments', filter=Q(enrollments__status='active')),
            revenue=Coalesce(
                Sum('enrollments__course__price', filter=Q(enrollments__status='active')),
                0,
                output_field=DecimalField()
            )
        ).order_by('-student_count')[:5]

        data = {
            "context": context_label,
            "metrics": {
                "total_courses": total_courses,
                "active_tutors": active_tutors_count,
                "active_students": total_students,
                "total_revenue": total_revenue,
                "upcoming_events_count": upcoming_events_count,
                "total_events": total_events,
            },
            "upcoming_classes": DashboardLiveLessonSerializer(upcoming_classes_qs, many=True).data,
            "upcoming_events": DashboardEventMinimalSerializer(upcoming_events_list_qs, many=True, context={'request': request}).data,
            "best_performing_courses": DashboardCourseMinimalSerializer(best_courses_qs, many=True, context={'request': request}).data,
        }

        return Response(data, status=status.HTTP_200_OK)


class TutorRevenueView(APIView):
    """
    Context-aware revenue and payout data.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, format=None):
        user = request.user
        active_org = getattr(request, "active_organization", None)

        if active_org:
             membership = OrgMembership.objects.filter(user=user, organization=active_org).first()
             if membership and membership.role in ["admin", "owner"]:
                 wallet = getattr(active_org, "wallet", None)
                 context_label = "Organization Finance"
             else:
                 wallet = getattr(user, "wallet", None)
                 context_label = "Personal Finance"
        else:
            wallet = getattr(user, "wallet", None)
            context_label = "Personal Finance"

        if not wallet:
            if context_label == "Organization Finance":
                 wallet = Wallet.objects.create(owner_org=active_org)
            else:
                 wallet = Wallet.objects.create(owner_user=user)

        transactions = Transaction.objects.filter(wallet=wallet).order_by('-created_at')[:20]
        payouts = Payout.objects.filter(wallet=wallet).order_by('-created_at')[:10]

        payout_methods = TutorPayoutMethod.objects.filter(profile__user=user)

        data = {
            "context": context_label,
            "wallet": WalletSerializer(wallet).data,
            "recent_transactions": TransactionSerializer(transactions, many=True).data,
            "payout_history": PayoutSerializer(payouts, many=True).data,
            "payout_methods": TutorPayoutMethodSerializer(payout_methods, many=True).data,
        }
        return Response(data, status=status.HTTP_200_OK)

class TutorAnalyticsView(APIView):
    """
    Detailed analytics view.
    (Extends the dashboard summary with deeper data)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, format=None):
        user = request.user
        active_org = getattr(request, "active_organization", None)

        if active_org:
            courses_qs = Course.objects.filter(organization=active_org)
        else:
            courses_qs = Course.objects.filter(organization__isnull=True, creator=user)

        top_courses = courses_qs.annotate(
             total_students=Count('enrollments'),
             active_students=Count('enrollments', filter=Q(enrollments__status='active')),
             total_revenue=Coalesce(Sum('enrollments__course__price'), 0, output_field=DecimalField())
        ).order_by('-total_revenue')[:10]

        data = {
             "top_courses_detailed": list(top_courses.values(
                 'title', 'total_students', 'active_students', 'total_revenue', 'rating_avg'
             ))
        }
        return Response(data, status=status.HTTP_200_OK)


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