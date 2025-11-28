from django.contrib import admin
from .models import Wallet, Transaction, Payout


@admin.action(description='Mark selected payouts as Completed')
def mark_payout_completed(modeladmin, request, queryset):
    """Admin action to mark pending payouts as completed."""
    for payout in queryset:
        payout.mark_completed()
    modeladmin.message_user(request, f"{queryset.count()} payouts marked as completed.")


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("id", "get_owner_display", "balance", "currency", "updated_at")
    list_filter = ("currency", "created_at")
    search_fields = (
        "owner_user__username",
        "owner_org__name",
    )
    autocomplete_fields = ("owner_user", "owner_org")
    readonly_fields = ("balance", "created_at", "updated_at")

    @admin.display(description="Owner")
    def get_owner_display(self, obj):
        # Uses the model's __str__ method to display the owner's name/title
        return obj.__str__()


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("id", "wallet", "tx_type", "amount", "created_at")
    list_filter = ("tx_type", "created_at")
    search_fields = (
        "wallet__owner_user__username",
        "wallet__owner_org__name",
        "description",
    )
    autocomplete_fields = ("wallet",)
    readonly_fields = ("created_at",)


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = ("id", "wallet", "amount", "status", "reference", "created_at")
    list_filter = ("status", "created_at")
    search_fields = (
        "wallet__owner_user__username",
        "wallet__owner_org__name",
        "reference",
    )
    autocomplete_fields = ("wallet",)
    readonly_fields = ("processed_at", "created_at")
    actions = [mark_payout_completed]