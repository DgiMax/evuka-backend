from django.contrib import admin
from django.utils.html import format_html
from .models import Order, OrderItem

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    fields = ("item_type_display", "price", "quantity", "subtotal")
    readonly_fields = ("item_type_display", "price", "quantity", "subtotal")
    can_delete = False

    def item_type_display(self, obj):
        if obj.book: return f"Book: {obj.book.title}"
        if obj.course: return f"Course: {obj.course.title}"
        if obj.event: return f"Event: {obj.event.title}"
        if obj.organization: return f"Org: {obj.organization.name}"
        return "Unknown"
    item_type_display.short_description = "Item"

    def subtotal(self, obj):
        return f"{obj.price * obj.quantity:.2f}"

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_number",
        "user",
        "status_badge",
        "payment_status_badge",
        "total_amount",
        "amount_paid_display",
        "balance_display",
        "created_at"
    )
    list_filter = (
        "status",
        "payment_status",
        "is_distributed",
        ("created_at", admin.DateFieldListFilter)
    )
    search_fields = ("order_number", "user__username", "user__email", "notes")
    readonly_fields = ("order_number", "is_distributed", "created_at", "updated_at")
    autocomplete_fields = ("user",)
    save_on_top = True
    inlines = [OrderItemInline]

    fieldsets = (
        ("Order Identification", {
            "fields": (("order_number", "user"), "status", "is_distributed")
        }),
        ("Financial Summary", {
            "fields": (("total_amount", "payment_status"), "notes")
        }),
        ("Timestamps", {
            "classes": ("collapse",),
            "fields": ("created_at", "updated_at")
        }),
    )

    def status_badge(self, obj):
        colors = {"pending": "#f39c12", "paid": "#27ae60", "cancelled": "#c0392b", "refunded": "#2980b9"}
        return format_html(
            '<span style="color: white; background-color: {}; padding: 3px 8px; border-radius: 10px; font-weight: bold; font-size: 11px;">{}</span>',
            colors.get(obj.status, "#333"),
            obj.get_status_display()
        )
    status_badge.short_description = "Order Status"

    def payment_status_badge(self, obj):
        colors = {"unpaid": "#e74c3c", "partially_paid": "#e67e22", "paid": "#27ae60"}
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            colors.get(obj.payment_status, "#000"),
            obj.get_payment_status_display()
        )
    payment_status_badge.short_description = "Payment"

    def amount_paid_display(self, obj):
        return f"{obj.amount_paid:.2f}"
    amount_paid_display.short_description = "Paid"

    def balance_display(self, obj):
        balance = obj.total_amount - obj.amount_paid
        color = "red" if balance > 0 else "black"
        return format_html('<span style="color: {};">{:.2f}</span>', color, balance)
    balance_display.short_description = "Balance"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user").prefetch_related("items")

@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "purchased_item", "price", "quantity", "created_at_display")
    search_fields = ("order__order_number", "book__title", "course__title", "event__title", "organization__name")
    autocomplete_fields = ("order", "book", "course", "event", "organization")
    list_filter = ("order__status", "order__payment_status")

    def purchased_item(self, obj):
        return str(obj)
    purchased_item.short_description = "Linked Item"

    def created_at_display(self, obj):
        return obj.order.created_at
    created_at_display.short_description = "Order Date"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("order", "book", "course", "event", "organization")