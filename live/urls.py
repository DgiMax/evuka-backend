from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    LiveClassManagementViewSet,
    LiveHubViewSet,
    LiveLessonViewSet
)

router = DefaultRouter()

router.register(r"manage/classes", LiveClassManagementViewSet, basename="live-class-manage")

router.register(r"hub", LiveHubViewSet, basename="live-hub")

router.register(r"lessons", LiveLessonViewSet, basename="live-lesson")

urlpatterns = [
    path("", include(router.urls)),
]