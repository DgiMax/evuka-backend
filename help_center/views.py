from rest_framework import views, status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.db.models import Q
from .models import HelpCategory, HelpArticle
from .serializers import HelpCategorySerializer, HelpArticleSerializer


class HelpCenterView(views.APIView):
    permission_classes = [AllowAny]  # Publicly accessible

    def get(self, request):
        query = request.query_params.get('search', '').strip()

        if query:
            # Search Mode: Return flat list of matching articles
            articles = HelpArticle.objects.filter(
                Q(question__icontains=query) | Q(answer__icontains=query),
                is_published=True
            )[:10]  # Limit results
            serializer = HelpArticleSerializer(articles, many=True)
            return Response({'type': 'search_results', 'data': serializer.data})

        else:
            # Browse Mode: Return Categories + Top FAQs
            categories = HelpCategory.objects.all()

            # Fetch a few "Popular" FAQs (e.g., generic logic or specific flag)
            # Here we just take the first 5 published ones
            faqs = HelpArticle.objects.filter(is_published=True).order_by('-created_at')[:5]

            return Response({
                'type': 'browse',
                'categories': HelpCategorySerializer(categories, many=True).data,
                'faqs': HelpArticleSerializer(faqs, many=True).data
            })