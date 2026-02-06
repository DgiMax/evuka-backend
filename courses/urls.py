from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CourseViewSet, FilterOptionsView,
    LessonViewSet, CourseFormOptionsView, TutorCourseViewSet,
    CoursePreviewView, CourseDetailsPreviewView, QuizAttemptViewSet,
    CourseManagerViewSet, AssignmentSubmissionViewSet, CourseNoteViewSet,
    CourseDiscussionViewSet, CourseSearchAPIView, DownloadCertificateAPIView, VerifyCertificateAPIView
)

router = DefaultRouter()

router.register(r'lessons', LessonViewSet, basename='lesson')
router.register(r"courses", CourseViewSet, basename="courses")
router.register(r'quizzes', QuizAttemptViewSet, basename='quiz')
router.register(r"assignments", AssignmentSubmissionViewSet, basename="assignments")
router.register(r'course-notes', CourseNoteViewSet, basename='course-notes')
router.register(r'course-discussions', CourseDiscussionViewSet, basename='course-discussion')

router.register(r"tutor-courses", TutorCourseViewSet, basename="tutor-courses")
router.register(r'manage-course', CourseManagerViewSet, basename='manage-course')

urlpatterns = [
    path('filters/', FilterOptionsView.as_view(), name='course-filter-options'),
    path('courses/certificates/verify/<uuid:certificate_uid>/', VerifyCertificateAPIView.as_view(),
         name='api-verify-certificate'),
    path('courses/certificates/download/<uuid:certificate_uid>/', DownloadCertificateAPIView.as_view(),
         name='api-download-certificate'),
    path('courses/form-options/', CourseFormOptionsView.as_view(), name='course-form-options'),
    path('courses/search-selector/', CourseSearchAPIView.as_view(), name='course-search-selector'),

    path("courses/<slug:slug>/preview-details/", CourseDetailsPreviewView.as_view(), name="course-preview-details"),
    path("courses/<slug:slug>/preview-learning/", CoursePreviewView.as_view(), name="course-preview-learning"),

    path('', include(router.urls)),
]