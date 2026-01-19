import json
from django.contrib import admin
from django.utils.html import format_html
from django.contrib import messages
from .models import Payment, Refund
from .services.paystack import verify_transaction, refund_payment


class RefundInline(admin.TabularInline):
    model = Refund
    extra = 0
    readonly_fields = ("amount", "reason", "status", "requested_by_user", "created_at", "processed_at")
    can_delete = False
    show_change_link = True


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "reference_code",
        "user_email",
        "amount_display",
        "status_badge",
        "provider",
        "created_at"
    )
    list_filter = ("provider", "status", "payment_method", "created_at")
    search_fields = (
        "reference_code",
        "transaction_id",
        "user__email",
        "order__id"
    )
    readonly_fields = (
        "reference_code",
        "transaction_id",
        "pretty_metadata",
        "created_at",
        "updated_at"
    )
    inlines = [RefundInline]
    actions = ["verify_paystack_status"]

    def user_email(self, obj):
        return obj.user.email

    def amount_display(self, obj):
        return f"{obj.currency} {obj.amount}"

    def status_badge(self, obj):
        colors = {
            "successful": "green",
            "pending": "orange",
            "failed": "red",
            "refunded": "purple"
        }
        color = colors.get(obj.status, "black")
        return format_html(
            '<span style="color:white; background-color:{}; padding:3px 8px; border-radius:3px;">{}</span>',
            color, obj.status.upper()
        )

    status_badge.short_description = "Status"

    def pretty_metadata(self, obj):
        """Display JSON metadata in a readable format"""
        return format_html("<pre>{}</pre>", json.dumps(obj.metadata, indent=4))

    pretty_metadata.short_description = "Metadata (JSON)"

    @admin.action(description="Verify selected payments with Paystack")
    def verify_paystack_status(self, request, queryset):
        """
        Manual trigger to check Paystack status for stuck payments.
        """
        count = 0
        for payment in queryset:
            if payment.provider != 'paystack':
                continue

            # Call our service
            response = verify_transaction(payment.reference_code)

            if response.get("status") and response["data"]["status"] == "success":
                payment.status = "successful"
                payment.transaction_id = str(response["data"]["id"])
                payment.save()
                count += 1

        self.message_user(request, f"{count} payments verified and updated.", messages.SUCCESS)


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = (
        "id", "payment_link", "amount", "status",
        "requested_by_user", "created_at"
    )
    list_filter = ("status", "requested_by_user")
    search_fields = ("payment__reference_code",)
    readonly_fields = ("created_at", "processed_at")

    def payment_link(self, obj):
        return obj.payment.reference_code