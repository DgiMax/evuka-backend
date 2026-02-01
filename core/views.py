from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import Count
from rest_framework.permissions import AllowAny
from books.models import BookCategory
from core.serializers import NavLinkCourseCategorySerializer, NavLinkBookCategorySerializer
from courses.models import GlobalCategory


class QuickNavDataView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        popular_course_cats = GlobalCategory.objects.annotate(
            total_items=Count('subcategories__courses')
        ).order_by('-total_items')[:10]

        popular_book_cats = BookCategory.objects.annotate(
            total_items=Count('books')
        ).order_by('-total_items')[:10]

        return Response({
            "courses": NavLinkCourseCategorySerializer(popular_course_cats, many=True).data,
            "books": NavLinkBookCategorySerializer(popular_book_cats, many=True).data
        })