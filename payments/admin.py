from django.contrib import admin
from .models import Payment, Refund


class RefundInline(admin.TabularInline):
    model = Refund
    extra = 0
    readonly_fields = ("amount", "reason", "status", "requested_by_user", "created_at", "processed_at")
    can_delete = False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id", "order", "user", "provider", "payment_method",
        "amount", "status", "transaction_id", "created_at",
    )
    list_filter = ("provider", "payment_method", "status", "created_at")
    search_fields = (
        "order__order_number",
        "user__username",
        "user__email",
        "transaction_id",
        "reference_code",
    )
    readonly_fields = (
        "reference_code", "transaction_id", "metadata",
        "created_at", "updated_at",
    )
    inlines = [RefundInline]


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = (
        "id", "payment", "amount", "status",
        "requested_by_user", "created_at", "processed_at",
    )
    list_filter = ("status", "requested_by_user", "created_at")
    search_fields = (
        "payment__transaction_id",
        "payment__reference_code",
        "reason",
    )
    readonly_fields = ("created_at", "processed_at")

