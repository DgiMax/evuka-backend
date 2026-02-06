from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from DVuka_Backend.search_service import UnifiedSearchService
from courses.models import Enrollment
from events.models import EventRegistration
from books.models import BookAccess

class UnifiedSearchView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        query = request.GET.get('q', '').strip()

        if not query or len(query) < 3:
            return Response({
                'courses': [], 'events': [], 'organizations': [], 'books': []
            })

        search_service = UnifiedSearchService(user=request.user, query=query)
        results = search_service.get_results()

        return Response(results)


class CartValidationView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        items = request.data.get('items', [])
        to_remove = []
        messages = []

        for item in items:
            itype = item.get('type')
            slug = item.get('slug')
            title = item.get('title')

            already_owned = False

            if itype == 'course':
                already_owned = Enrollment.objects.filter(
                    user=request.user, course__slug=slug, status='active'
                ).exists()
            elif itype == 'event':
                already_owned = EventRegistration.objects.filter(
                    user=request.user, event__slug=slug, status='registered'
                ).exists()
            elif itype == 'book':
                already_owned = BookAccess.objects.filter(
                    user=request.user, book__slug=slug
                ).exists()

            if already_owned:
                to_remove.append(slug)
                messages.append(f"You already have access to '{title}'. It has been removed from your cart.")

        return Response({
            "valid": len(to_remove) == 0,
            "removed_slugs": to_remove,
            "messages": messages
        })