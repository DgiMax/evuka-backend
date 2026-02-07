from django.contrib import admin
from django.utils.html import format_html
from django.contrib import messages
import json
from .models import Payment, Refund

class RefundInline(admin.TabularInline):
    model = Refund
    extra = 0
    fields = ("amount", "status", "reason", "requested_by_user", "created_at", "processed_at")
    readonly_fields = ("amount", "reason", "status", "requested_by_user", "created_at", "processed_at")
    can_delete = False
    show_change_link = True

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "reference_code",
        "user_email",
        "amount_currency",
        "status_badge",
        "payment_method",
        "provider",
        "created_at"
    )
    list_filter = (
        "status", 
        "provider", 
        "payment_method", 
        ("created_at", admin.DateFieldListFilter)
    )
    search_fields = (
        "reference_code", 
        "transaction_id", 
        "user__email", 
        "user__username",
        "order__order_number"
    )
    autocomplete_fields = ("order", "user")
    readonly_fields = (
        "reference_code", 
        "transaction_id", 
        "pretty_metadata", 
        "created_at", 
        "updated_at"
    )
    inlines = [RefundInline]
    actions = ["verify_paystack_status"]
    save_on_top = True

    fieldsets = (
        ("Transaction Details", {
            "fields": (("order", "user"), ("amount", "currency"), ("status", "provider", "payment_method"))
        }),
        ("Identifiers", {
            "fields": (("reference_code", "transaction_id"),)
        }),
        ("Technical Data", {
            "classes": ("collapse",),
            "fields": ("pretty_metadata", ("created_at", "updated_at"))
        }),
    )

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = "User Email"

    def amount_currency(self, obj):
        return f"{obj.currency} {obj.amount}"
    amount_currency.short_description = "Total Amount"

    def status_badge(self, obj):
        colors = {
            "successful": "#27ae60",
            "pending": "#f39c12",
            "processing": "#3498db",
            "failed": "#c0392b",
            "refunded": "#8e44ad"
        }
        return format_html(
            '<span style="color: white; background-color: {}; padding: 4px 10px; border-radius: 12px; font-weight: bold; font-size: 11px;">{}</span>',
            colors.get(obj.status, "#333"), 
            obj.status.upper()
        )
    status_badge.short_description = "Status"

    def pretty_metadata(self, obj):
        return format_html("<pre>{}</pre>", json.dumps(obj.metadata, indent=4))
    pretty_metadata.short_description = "Raw Metadata"

    @admin.action(description="Verify Paystack Status (Sync with Gateway)")
    def verify_paystack_status(self, request, queryset):
        try:
            from .services.paystack import verify_transaction
            count = 0
            for payment in queryset.filter(provider='paystack'):
                response = verify_transaction(payment.reference_code)
                if response.get("status") and response["data"]["status"] == "success":
                    payment.status = "successful"
                    payment.transaction_id = str(response["data"]["id"])
                    payment.save()
                    from .models import update_order_payment_status
                    update_order_payment_status(payment.order)
                    count += 1
            self.message_user(request, f"{count} payments successfully verified and updated.", messages.SUCCESS)
        except Exception as e:
            self.message_user(request, f"Verification failed: {str(e)}", messages.ERROR)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user", "order")

@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ("payment_link", "amount_display", "status_badge", "requested_by_user", "created_at")
    list_filter = ("status", "requested_by_user", "created_at")
    search_fields = ("payment__reference_code", "reason")
    autocomplete_fields = ("payment",)
    readonly_fields = ("created_at", "processed_at")

    def payment_link(self, obj):
        return obj.payment.reference_code
    payment_link.short_description = "Payment Reference"

    def amount_display(self, obj):
        return f"{obj.payment.currency} {obj.amount}"
    amount_display.short_description = "Refund Amount"

    def status_badge(self, obj):
        colors = {"requested": "#f39c12", "processed": "#27ae60", "failed": "#c0392b"}
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            colors.get(obj.status, "#000"), obj.status.upper()
        )
    status_badge.short_description = "Status"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("payment")