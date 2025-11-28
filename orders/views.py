from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Order
from .serializers import OrderSerializer, PaymentSerializer


class OrderViewSet(viewsets.ModelViewSet):
    """
    Handles CRUD operations for Orders.
    Each order belongs to a user and can have multiple items and payments.
    """
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Return only the orders belonging to the logged-in user."""
        return Order.objects.filter(user=self.request.user).order_by("-created_at")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        serializer.save()

    @action(detail=True, methods=["post"], url_path="add-payment")
    def add_payment(self, request, pk=None):
        """
        Allows user (or a payment processor) to add a payment record
        to an existing order. Useful for partial or manual payments.
        """
        order = self.get_object()

        serializer = PaymentSerializer(data=request.data, context={"request": request})

        if serializer.is_valid():
            payment = serializer.save(order=order, user=request.user)
            order.update_payment_status()

            return Response({
                "message": "Payment recorded successfully",
                "payment": PaymentSerializer(payment).data,
                "order": OrderSerializer(order, context={"request": request}).data
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)