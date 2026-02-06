from rest_framework import viewsets, mixins, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django.http import HttpResponse
from rest_framework.parsers import MultiPartParser, FormParser
from django.shortcuts import get_object_or_404
from django.http import FileResponse, HttpResponseForbidden
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from weasyprint import HTML
from django.db.models import Count, Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.views import APIView
from django.utils import timezone
from rest_framework import serializers
from django.db.models import Sum, Count, F
from django.db.models.functions import TruncMonth
from rest_framework import generics, filters, permissions
from django.template.loader import render_to_string

from revenue.models import Wallet
from .filters import BookFilter
from .serializers import BookShortSerializer, DashboardBookPerformanceSerializer, BookReaderContentSerializer
from django.db.models import F, Sum, Count, Q, DecimalField, Value
from django.db.models.functions import Coalesce, TruncMonth
from decimal import Decimal
from rest_framework.views import APIView
from rest_framework.response import Response
from django.utils import timezone
from datetime import timedelta

from .models import Book, BookCategory, BookSubCategory, BookAccess
from .serializers import (
    BookListSerializer,
    BookDetailSerializer,
    BookCreateUpdateSerializer,
    BookCategorySerializer,
    BookSubCategoryOptionSerializer
)
from .permissions import IsPublisher, IsBookOwner


class PublicBookViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.AllowAny]
    lookup_field = "slug"
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]

    # Use the new FilterSet class instead of the basic fields list
    filterset_class = BookFilter

    search_fields = ["title", "authors", "short_description", "tags"]
    ordering_fields = ["created_at", "rating_avg", "price", "sales_count"]

    def get_queryset(self):
        return Book.objects.filter(status='published').select_related(
            'publisher_profile', 'publisher_profile__user'
        ).prefetch_related('categories', 'subcategories').order_by("-created_at")

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return BookDetailSerializer
        return BookListSerializer

    @action(detail=False, methods=["get"], url_path="most-popular")
    def most_popular(self, request):
        queryset = self.get_queryset().order_by("-sales_count", "-view_count")[:6]
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="categories")
    def categories(self, request):
        categories = BookCategory.objects.all().order_by('name')
        return Response(BookCategorySerializer(categories, many=True).data)

    @action(
        detail=True,
        methods=["get"],
        permission_classes=[permissions.IsAuthenticated],
        url_path="read"
    )
    def read_book(self, request, slug=None):
        book = self.get_object()
        user = request.user

        has_access = BookAccess.objects.filter(user=user, book=book).exists()
        is_owner = book.created_by == user

        if not has_access and not is_owner:
            return Response(
                {"detail": "You must purchase this book to read it."},
                status=status.HTTP_403_FORBIDDEN
            )

        if not book.book_file:
            return Response(
                {"detail": "Book file not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        response = FileResponse(book.book_file.open('rb'), content_type='application/pdf')
        response["Content-Disposition"] = f'inline; filename="{book.slug}.pdf"'
        return response


class PublisherBookViewSet(viewsets.ModelViewSet):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [permissions.IsAuthenticated, IsPublisher]
    lookup_field = "slug"
    filter_backends = [filters.SearchFilter, filters.OrderingFilter, DjangoFilterBackend]
    search_fields = ["title", "isbn"]
    ordering_fields = ["created_at", "sales_count"]
    filterset_fields = ['status']

    def get_queryset(self):
        return Book.objects.filter(created_by=self.request.user).select_related(
            'publisher_profile'
        ).prefetch_related('categories', 'subcategories').order_by("-updated_at")

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return BookCreateUpdateSerializer
        if self.action == "retrieve":
            return BookDetailSerializer
        return BookListSerializer

    def perform_create(self, serializer):
        user = self.request.user
        publisher_profile = getattr(user, "publisher_profile", None)

        if not publisher_profile:
            raise serializers.ValidationError(
                {"error": "User does not have a Publisher Profile. Please onboard first."}
            )

        serializer.save(
            created_by=user,
            publisher_profile=publisher_profile
        )

    def perform_update(self, serializer):
        serializer.save()

    @action(detail=True, methods=["post"], url_path="archive")
    def archive_book(self, request, slug=None):
        book = self.get_object()

        if book.status == 'archived':
            book.status = 'draft'
            msg = "Book restored to Drafts."
        else:
            book.status = 'archived'
            msg = "Book archived successfully."

        book.save()
        return Response({"message": msg, "status": book.status})


class BookFormOptionsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        categories = BookCategory.objects.all().order_by('name')
        subcategories = BookSubCategory.objects.select_related('category').all().order_by('name')

        return Response({
            "categories": BookCategorySerializer(categories, many=True).data,
            "subcategories": BookSubCategoryOptionSerializer(subcategories, many=True).data,
        })


class PublisherAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        now = timezone.now()
        six_months_ago = now - timedelta(days=180)

        COMMISSION_RATE = Decimal('0.10')
        NET_PERCENTAGE = Decimal('1.00') - COMMISSION_RATE

        books_qs = Book.objects.filter(created_by=user)

        kpi_data = BookAccess.objects.filter(book__in=books_qs).aggregate(
            total_revenue=Sum(
                Coalesce(F('book__price'), Value(0)) * NET_PERCENTAGE,
                output_field=DecimalField()
            ),
            total_sales=Count('id'),
            total_readers=Count('user', distinct=True)
        )

        total_views = books_qs.aggregate(total=Sum('view_count'))['total'] or 0

        performance_list = books_qs.annotate(
            actual_sales=Count('readers'),
            revenue=Coalesce(
                Sum(
                    Coalesce(F('price'), Value(0)) * NET_PERCENTAGE,
                    output_field=DecimalField()
                ),
                Decimal('0')
            )
        ).order_by('-actual_sales')[:10]

        monthly_trend = BookAccess.objects.filter(
            book__in=books_qs,
            granted_at__gte=six_months_ago
        ).annotate(
            month=TruncMonth('granted_at')
        ).values('month').annotate(
            revenue=Sum(
                Coalesce(F('book__price'), Value(0)) * NET_PERCENTAGE,
                output_field=DecimalField()
            ),
            sales=Count('id')
        ).order_by('month')

        graph_data = []
        for entry in monthly_trend:
            graph_data.append({
                "name": entry['month'].strftime("%b"),
                "revenue": float(entry['revenue'] or 0),
                "sales": entry['sales']
            })

        return Response({
            "kpi": {
                "total_revenue": float(kpi_data['total_revenue'] or 0),
                "total_sales": kpi_data['total_sales'],
                "total_views": total_views,
                "total_readers": kpi_data['total_readers']
            },
            "top_books": DashboardBookPerformanceSerializer(performance_list, many=True).data,
            "graph_data": graph_data
        })


class BookLookupView(generics.ListAPIView):
    queryset = Book.objects.filter(status='published')
    serializer_class = BookShortSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ['title', 'authors', 'isbn']
    pagination_class = None


class BookFiltersView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        categories = BookCategory.objects.all().order_by('name')
        subcategories = BookSubCategory.objects.select_related('category').all()

        return Response({
            "globalCategories": BookCategorySerializer(categories, many=True).data,
            "globalSubCategories": [
                {
                    "id": sub.id,
                    "name": sub.name,
                    "slug": sub.slug,
                    "parent_slug": sub.category.slug
                } for sub in subcategories
            ],
            "globalLevels": [
                {"id": "beginner", "name": "Beginner"},
                {"id": "intermediate", "name": "Intermediate"},
                {"id": "advanced", "name": "Advanced"},
                {"id": "all_levels", "name": "All Levels"},
            ],
            "price": {
                "min": 0,
                "max": 20000
            }
        })


class ExportPublisherPDFView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        now = timezone.now()

        COMMISSION_RATE = Decimal('0.10')
        NET_PERCENTAGE = Decimal('1.00') - COMMISSION_RATE

        wallet, _ = Wallet.objects.get_or_create(owner_user=user)
        books_qs = Book.objects.filter(created_by=user)

        metrics = self._calculate_book_metrics(books_qs, wallet, NET_PERCENTAGE)

        performance_list = books_qs.annotate(
            actual_sales=Count('readers'),
            revenue=Coalesce(
                Sum(
                    Coalesce(F('price'), Value(0)) * NET_PERCENTAGE,
                    output_field=DecimalField()
                ),
                Decimal('0')
            )
        ).order_by('-actual_sales')

        context = {
            'publisher': user.get_full_name() or user.username,
            'metrics': metrics,
            'books': performance_list,
            'date': now.strftime("%B %d, %Y"),
        }

        html_string = render_to_string('pdf/publisher_report.html', context)

        html = HTML(string=html_string, base_url=request.build_absolute_uri())
        pdf_file = html.write_pdf()

        response = HttpResponse(pdf_file, content_type='application/pdf')
        filename = f"Publisher_Report_{now.strftime('%Y%m%d')}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        return response

    def _calculate_book_metrics(self, books_qs, wallet, net_pct):
        book_revenue = BookAccess.objects.filter(
            book__in=books_qs
        ).aggregate(
            total=Sum(
                Coalesce(F('book__price'), Value(0)) * net_pct,
                output_field=DecimalField()
            )
        )['total'] or Decimal('0')

        total_readers = BookAccess.objects.filter(book__in=books_qs).values('user').distinct().count()
        total_views = books_qs.aggregate(total=Sum('view_count'))['total'] or 0

        return {
            "total_books": books_qs.count(),
            "published_count": books_qs.filter(status='published').count(),
            "total_readers": total_readers,
            "total_views": total_views,
            "available_balance": float(wallet.balance),
            "net_book_revenue": float(book_revenue),
        }


class MyLibraryListView(generics.ListAPIView):
    serializer_class = BookListSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return Book.objects.filter(readers__user=user, status='published').distinct()

class BookReaderDetailView(generics.RetrieveAPIView):
    serializer_class = BookReaderContentSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'slug'

    def get_queryset(self):
        user = self.request.user
        return Book.objects.filter(readers__user=user, status='published')

