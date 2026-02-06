from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import HelpCategoryViewSet, HelpArticleViewSet

router = DefaultRouter()
router.register(r'categories', HelpCategoryViewSet, basename='help-category')
router.register(r'articles', HelpArticleViewSet, basename='help-article')

urlpatterns = [
    path('', include(router.urls)),
]