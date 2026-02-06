from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.db.models import Q, F
from .models import HelpCategory, HelpArticle
from .serializers import HelpCategorySerializer, HelpArticleSerializer


class HelpCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = HelpCategory.objects.all()
    serializer_class = HelpCategorySerializer
    permission_classes = [AllowAny]
    lookup_field = 'slug'


class HelpArticleViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = HelpArticle.objects.filter(is_published=True)
    serializer_class = HelpArticleSerializer
    permission_classes = [AllowAny]
    lookup_field = 'slug'

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.query_params.get('search')
        category_slug = self.request.query_params.get('category')

        if query:
            queryset = queryset.filter(
                Q(question__icontains=query) | Q(answer__icontains=query)
            )

        if category_slug:
            queryset = queryset.filter(category__slug=category_slug)

        return queryset

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        HelpArticle.objects.filter(pk=instance.pk).update(views_count=F('views_count') + 1)
        return super().retrieve(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    def feedback(self, request, slug=None):
        article = self.get_object()
        is_helpful = request.data.get('helpful')

        if is_helpful:
            HelpArticle.objects.filter(pk=article.pk).update(helpful_count=F('helpful_count') + 1)
        else:
            HelpArticle.objects.filter(pk=article.pk).update(not_helpful_count=F('not_helpful_count') + 1)

        return Response({'status': 'feedback received'}, status=status.HTTP_200_OK)