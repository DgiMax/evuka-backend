from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import LiveClassViewSet, LiveLessonViewSet, AllLiveClassesViewSet

router = DefaultRouter()
router.register(r"classes", LiveClassViewSet, basename="live-class")
router.register(r"lessons", LiveLessonViewSet, basename="live-lesson")
router.register(r'all-classes', AllLiveClassesViewSet, basename='all-live-classes')

urlpatterns = [
    path("", include(router.urls)),
]