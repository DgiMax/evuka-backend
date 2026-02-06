from django.urls import path, include
from rest_framework.routers import SimpleRouter
from . import views
from .views import StudentRegisteredEventsViewSet

router = SimpleRouter()
router.register(r'tutor-events', views.TutorEventViewSet, basename='tutor-events')
router.register(r'registered-events', StudentRegisteredEventsViewSet, basename='student-registered-events')
router.register(r'', views.PublicEventViewSet, basename='events')

urlpatterns = [
    path('filter-options/', views.EventFilterOptionsView.as_view(), name='event-filter-options'),
    path('', include(router.urls)),
]
