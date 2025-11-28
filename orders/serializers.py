from django.db import transaction
from rest_framework import serializers
from events.models import Event
from .models import Order, OrderItem
from payments.models import Payment
from courses.models import Course


class OrderItemSerializer(serializers.ModelSerializer):
    item_title = serializers.SerializerMethodField()

    course = serializers.SlugRelatedField(
        queryset=Course.objects.all(),
        slug_field='slug',
        required=False,
        allow_null=True
    )

    event = serializers.SlugRelatedField(
        queryset=Event.objects.all(),
        slug_field='slug',
        required=False,
        allow_null=True
    )

    class Meta:
        model = OrderItem
        fields = ["id", "course", "event", "price", "quantity", "item_title"]

    def validate(self, data):
        if not data.get("course") and not data.get("event"):
            raise serializers.ValidationError("Each item must have either a course or an event.")
        if data.get("course") and data.get("event"):
            raise serializers.ValidationError("Each item can only have one of: course or event.")
        return data

    def get_item_title(self, obj):
        if obj.course:
            return obj.course.title
        if obj.event:
            return obj.event.title
        return None


class PaymentSerializer(serializers.ModelSerializer):
    method_display = serializers.CharField(source="get_method_display", read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id", "reference_code", "amount", "status",
            "payment_method", "method_display", "created_at"
        ]
        read_only_fields = ["status", "created_at", "method_display"]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True)
    payments = PaymentSerializer(many=True, read_only=True)
    order_number = serializers.ReadOnlyField()
    total_amount = serializers.ReadOnlyField()
    status = serializers.ReadOnlyField()
    amount_paid = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = Order
        fields = [
            "id", "order_number", "user", "total_amount", "amount_paid",
            "status", "payment_status", "notes", "created_at",
            "updated_at", "items", "payments"
        ]
        read_only_fields = ["created_at", "updated_at"]

    def create(self, validated_data):
        items_data = validated_data.pop("items", [])

        with transaction.atomic():
            order = Order.objects.create(**validated_data)

            total = 0
            for item_data in items_data:
                event = item_data.get('event')
                course = item_data.get('course')

                if event:
                    if event.is_full():
                        raise serializers.ValidationError(
                            f"Sorry, the event '{event.title}' is now full and cannot be purchased."
                        )

                item = OrderItem.objects.create(order=order, **item_data)

                total += item.price * item.quantity

            order.total_amount = total
            order.save()

        return order