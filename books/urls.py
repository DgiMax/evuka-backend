from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PublicBookViewSet, PublisherBookViewSet, BookFormOptionsView, PublisherAnalyticsView, BookLookupView, \
    BookFiltersView, ExportPublisherPDFView, BookReaderDetailView, MyLibraryListView

router = DefaultRouter()
router.register(r'marketplace', PublicBookViewSet, basename='public-books')
router.register(r'manage', PublisherBookViewSet, basename='publisher-books')

urlpatterns = [
    path('filters/', BookFiltersView.as_view(), name='book-filters'),
    path('form-options/', BookFormOptionsView.as_view(), name='book-form-options'),
    path('analytics/', PublisherAnalyticsView.as_view(), name='publisher-analytics'),
    path('lookup/', BookLookupView.as_view(), name='book-lookup'),

    path('dashboard/publisher/export-pdf/', ExportPublisherPDFView.as_view(), name='publisher-export-pdf'),
    path('my-library/', MyLibraryListView.as_view(), name='my-library-list'),
    path('library/<slug:slug>/read/', BookReaderDetailView.as_view(), name='book-read-content'),
    path('', include(router.urls)),
]