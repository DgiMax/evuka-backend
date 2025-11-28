from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db.models import Q
from .models import Wishlist
from .serializers import WishlistSerializer


class WishlistViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing a user's wishlist items (courses & events).
    """

    serializer_class = WishlistSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Return all wishlist items for the logged-in user."""
        return Wishlist.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        """Attach the logged-in user when creating a wishlist item."""
        serializer.save(user=self.request.user)

    @action(detail=False, methods=["delete"], url_path=r"remove/(?P<slug>[-\w]+)")
    def remove_by_slug(self, request, slug=None):
        """
        Remove a wishlist item by its course or event slug.
        """
        user = request.user

        wishlist_item = (
            Wishlist.objects.filter(user=user)
            .filter(Q(course__slug=slug) | Q(event__slug=slug))
            .first()
        )

        if not wishlist_item:
            return Response(
                {"detail": "Item not found in your wishlist."},
                status=status.HTTP_404_NOT_FOUND,
            )

        item_type = wishlist_item.item_type
        item_title = wishlist_item.item_title

        wishlist_item.delete()

        response_data = {
            "detail": f"{item_type.capitalize()} '{item_title}' was removed from your wishlist.",
            "type": item_type,
            "slug": slug,
        }

        return Response(response_data, status=status.HTTP_200_OK)