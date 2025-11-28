from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

tutor_router = DefaultRouter()
tutor_router.register(
    r'manage',
    views.TutorAnnouncementViewSet,
    basename='tutor-announcement'
)

student_router = DefaultRouter()
student_router.register(
    r'',
    views.StudentAnnouncementViewSet,
    basename='student-announcement'
)

urlpatterns = [
    path(
        'tutor/target-courses/',
        views.TargetableCoursesListView.as_view(),
        name='tutor-target-courses'
    ),
    path('tutor/', include(tutor_router.urls)),
    path('', include(student_router.urls)),
]