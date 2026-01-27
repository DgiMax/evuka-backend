from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PublicBookViewSet, PublisherBookViewSet, BookFormOptionsView, PublisherAnalyticsView, BookLookupView

router = DefaultRouter()
router.register(r'marketplace', PublicBookViewSet, basename='public-books')
router.register(r'manage', PublisherBookViewSet, basename='publisher-books')

urlpatterns = [
    path('form-options/', BookFormOptionsView.as_view(), name='book-form-options'),
    path('analytics/', PublisherAnalyticsView.as_view(), name='publisher-analytics'),
    path('lookup/', BookLookupView.as_view(), name='book-lookup'),
    path('', include(router.urls)),
]