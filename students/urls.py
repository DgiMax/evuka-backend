from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TutorStudentsViewSet

router = DefaultRouter()
router.register(r"", TutorStudentsViewSet, basename="tutor-students")

urlpatterns = [
    path("", include(router.urls)),
]
