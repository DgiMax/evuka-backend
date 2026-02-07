from django.contrib import admin
from django.utils.html import format_html
from django.contrib import messages
from .models import Wallet, Transaction, Payout

@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("owner_display", "balance_display", "currency", "updated_at")
    list_filter = ("currency", ("created_at", admin.DateFieldListFilter))
    search_fields = (
        "owner_user__email",
        "owner_user__username",
        "owner_org__name",
    )
    readonly_fields = ("balance", "created_at", "updated_at")
    autocomplete_fields = ("owner_user", "owner_org")
    save_on_top = True

    fieldsets = (
        ("Ownership", {
            "fields": (("owner_user", "owner_org"),)
        }),
        ("Financial Data", {
            "fields": (("balance", "currency"),)
        }),
        ("Timestamps", {
            "classes": ("collapse",),
            "fields": ("created_at", "updated_at")
        }),
    )

    def owner_display(self, obj):
        if obj.owner_user:
            return format_html("👤 <b>{}</b>", obj.owner_user.email)
        elif obj.owner_org:
            return format_html("🏢 <b>{}</b>", obj.owner_org.name)
        return "System"
    owner_display.short_description = "Owner"

    def balance_display(self, obj):
        return f"{obj.currency} {obj.balance:,.2f}"
    balance_display.short_description = "Current Balance"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("owner_user", "owner_org")

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("reference_short", "wallet_link", "tx_type_badge", "amount_display", "created_at")
    list_filter = ("tx_type", ("created_at", admin.DateFieldListFilter))
    search_fields = (
        "reference",
        "description",
        "wallet__owner_user__email",
        "wallet__owner_org__name",
    )
    readonly_fields = (
        "wallet", "tx_type", "amount", "balance_after",
        "reference", "created_at", "description",
        "content_type", "object_id", "content_object"
    )

    def reference_short(self, obj):
        return f"TXN-{str(obj.reference)[:8].upper()}"
    reference_short.short_description = "Reference"

    def wallet_link(self, obj):
        return obj.wallet
    wallet_link.short_description = "Wallet Source"

    def amount_display(self, obj):
        color = "#27ae60" if obj.amount > 0 else "#e74c3c"
        return format_html('<span style="color: {}; font-weight: bold;">{:,.2f}</span>', color, obj.amount)
    amount_display.short_description = "Amount"

    def tx_type_badge(self, obj):
        colors = {
            "credit": "#27ae60",
            "debit": "#e74c3c",
            "fee": "#f39c12",
            "refund": "#8e44ad"
        }
        return format_html(
            '<span style="color: white; background-color: {}; padding: 3px 8px; border-radius: 10px; font-size: 10px; font-weight: bold;">{}</span>',
            colors.get(obj.tx_type, "#7f8c8d"),
            obj.tx_type.upper()
        )
    tx_type_badge.short_description = "Type"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("wallet__owner_user", "wallet__owner_org")

@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = ("reference_short", "wallet", "amount_formatted", "status_badge", "created_at")
    list_filter = ("status", ("created_at", admin.DateFieldListFilter))
    search_fields = ("reference", "wallet__owner_user__email", "wallet__owner_org__name")
    readonly_fields = ("reference", "processed_at", "created_at", "failure_reason")
    actions = ["retry_payout_processing"]

    def reference_short(self, obj):
        return str(obj.reference)[:8].upper()
    reference_short.short_description = "ID"

    def amount_formatted(self, obj):
        return f"{obj.wallet.currency} {obj.amount:,.2f}"
    amount_formatted.short_description = "Amount"

    def status_badge(self, obj):
        colors = {
            "completed": "#27ae60",
            "processing": "#3498db",
            "pending": "#f39c12",
            "failed": "#c0392b"
        }
        return format_html(
            '<span style="color: white; background-color: {}; padding: 4px 10px; border-radius: 12px; font-weight: bold; font-size: 11px;">{}</span>',
            colors.get(obj.status, "#7f8c8d"),
            obj.status.upper()
        )
    status_badge.short_description = "Status"

    @admin.action(description="Retry selected payouts")
    def retry_payout_processing(self, request, queryset):
        from .tasks import process_single_payout
        count = 0
        for payout in queryset.filter(status__in=['pending', 'failed']):
            payout.status = 'pending'
            payout.save()
            process_single_payout(payout.id)
            count += 1
        self.message_user(request, f"{count} payouts re-queued for processing.", messages.INFO)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("wallet__owner_user", "wallet__owner_org")