from django.contrib import admin
from .models import Order, OrderItem
from payments.models import Payment


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("price", "quantity")


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    readonly_fields = ("reference_code", "amount", "payment_method", "status", "created_at")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_number", "user", "status", "payment_status",
        "total_amount", "amount_paid_display", "balance_display", "created_at"
    )
    list_filter = ("status", "payment_status", "created_at")
    search_fields = ("order_number", "user__username", "user__email")
    inlines = [OrderItemInline, PaymentInline]
    readonly_fields = ("order_number", "created_at", "updated_at")

    def amount_paid_display(self, obj):
        return f"{obj.amount_paid:.2f}"
    amount_paid_display.short_description = "Amount Paid"

    def balance_display(self, obj):
        return f"{obj.total_amount - obj.amount_paid:.2f}"
    balance_display.short_description = "Balance"


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "course", "event", "price", "quantity")
    search_fields = ("order__order_number", "course__title", "event__title")
    autocomplete_fields = ("order", "course", "event")