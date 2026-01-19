from django.contrib import admin
from django.utils.html import format_html
from django.contrib import messages
from .models import Wallet, Transaction, Payout
from .tasks import process_single_payout  # Import the logic to retry


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("id", "owner_display", "balance_display", "currency", "updated_at")
    list_filter = ("currency", "created_at")
    search_fields = (
        "owner_user__email",
        "owner_user__username",
        "owner_org__name",
    )
    # CRITICAL: Prevent manual editing of balance to maintain ledger integrity
    readonly_fields = ("balance", "created_at", "updated_at")

    def owner_display(self, obj):
        if obj.owner_user:
            return f"User: {obj.owner_user.email}"
        elif obj.owner_org:
            return f"Org: {obj.owner_org.name}"
        return "System/Orphan"

    owner_display.short_description = "Owner"

    def balance_display(self, obj):
        return f"{obj.currency} {obj.balance:,.2f}"

    balance_display.short_description = "Balance"


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("reference", "wallet_link", "tx_type_badge", "amount", "created_at")
    list_filter = ("tx_type", "created_at")
    search_fields = (
        "wallet__owner_user__email",
        "reference",
        "description",
    )
    readonly_fields = ("wallet", "tx_type", "amount", "balance_after", "reference", "created_at", "description")

    def wallet_link(self, obj):
        return obj.wallet

    wallet_link.short_description = "Wallet"

    def tx_type_badge(self, obj):
        colors = {
            "credit": "green",
            "debit": "red",
            "fee": "orange",
            "refund": "purple"
        }
        return format_html(
            '<span style="color:white; background-color:{}; padding:3px 8px; border-radius:3px;">{}</span>',
            colors.get(obj.tx_type, "grey"),
            obj.tx_type.upper()
        )

    tx_type_badge.short_description = "Type"


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = ("reference", "wallet", "amount", "status_badge", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("reference", "wallet__owner_user__email")
    readonly_fields = ("processed_at", "created_at", "failure_reason")
    actions = ["retry_payout_processing"]

    def status_badge(self, obj):
        colors = {
            "completed": "green",
            "processing": "blue",
            "pending": "orange",
            "failed": "red"
        }
        return format_html(
            '<span style="color:white; background-color:{}; padding:3px 8px; border-radius:3px;">{}</span>',
            colors.get(obj.status, "grey"),
            obj.status.upper()
        )

    status_badge.short_description = "Status"

    @admin.action(description="Retry processing selected payouts")
    def retry_payout_processing(self, request, queryset):
        """
        Manually trigger the payout logic for stuck items.
        """
        count = 0
        for payout in queryset:
            if payout.status in ['pending', 'failed']:
                # Reset status to pending to allow retry
                payout.status = 'pending'
                payout.save()
                # Call the task function directly (synchronously)
                process_single_payout(payout.id)
                count += 1

        self.message_user(request, f"{count} payouts queued for retry.", messages.INFO)