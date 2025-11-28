from django.contrib import admin
from .models import Wishlist


@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "item_type_display", "item_title", "created_at")
    list_filter = ("created_at", "user")
    search_fields = ("user__username", "course__title", "event__title")
    autocomplete_fields = ("user", "course", "event")
    readonly_fields = ("created_at",)

    @admin.display(description="Type")
    def item_type_display(self, obj):
        # Uses the @property item_type defined in the models.py
        return obj.item_type