from django.urls import path, include
from rest_framework.routers import SimpleRouter
from .views import (
    RegisterView,
    VerifyEmailView,
    LoginView,
    ForgotPasswordView,
    ResetPasswordView,
    ChangePasswordView,
    ResendVerificationView,
    LogoutView,
    CurrentUserView,
    CookieTokenRefreshView,
    DashboardAPIView,
    CreatorProfileManageView,
    StudentProfileManageView, TutorDashboardView, TutorRevenueView, TutorAnalyticsView,
    PublicTutorViewSet, GetWebSocketTokenView, NewsletterSubscribeView,
)

app_name = "users"

router = SimpleRouter()

router.register(r'tutors', PublicTutorViewSet, basename='public-tutors')

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("verify-email/", VerifyEmailView.as_view(), name="verify-email"),
    path("resend-verification/", ResendVerificationView.as_view(), name="resend-verification"),

    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),

    path("forgot-password/", ForgotPasswordView.as_view(), name="forgot-password"),
    path("reset-password/<str:token>/", ResetPasswordView.as_view(), name="reset-password"),
    path("change-password/", ChangePasswordView.as_view(), name="change-password"),

    path("refresh/", CookieTokenRefreshView.as_view(), name="token_refresh"),
    path('newsletter/subscribe/', NewsletterSubscribeView.as_view(), name='newsletter-subscribe'),

    path("me/", CurrentUserView.as_view(), name="current-user"),
    path('dashboard/', DashboardAPIView.as_view(), name='api-dashboard'),

    path('profile/tutor/', CreatorProfileManageView.as_view(), name='manage-tutor-profile'),
    path('profile/student/', StudentProfileManageView.as_view(), name='manage-student-profile'),

    path('dashboard/tutor/', TutorDashboardView.as_view(), name='tutor-dashboard'),
    path('dashboard/revenue/', TutorRevenueView.as_view(), name='tutor-revenue'),
    path('dashboard/analytics/', TutorAnalyticsView.as_view(), name='tutor-analytics'),
    path('ws-token/', GetWebSocketTokenView.as_view(), name='get_ws_token'),

    path('', include(router.urls)),
]