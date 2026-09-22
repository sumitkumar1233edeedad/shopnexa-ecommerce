from django.contrib import admin
from .models import Cart, CartItem


class CartItemInline(admin.TabularInline):
    model = CartItem
    fields = ("product", "quantity", "total_price_display", "slug")
    readonly_fields = ("total_price_display", "slug")
    autocomplete_fields = ("product",)
    extra = 0
    show_change_link = True

    @admin.display(description="Total Price")
    def total_price_display(self, obj):
        return f"₹{obj.total_price}" if obj and obj.pk else "-"


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("user", "total_items_display", "total_price_display", "created_at", "slug")
    search_fields = ("user__username", "slug")
    readonly_fields = ("slug", "created_at", "total_items_display", "total_price_display")
    autocomplete_fields = ("user",)
    date_hierarchy = "created_at"
    inlines = [CartItemInline]
    list_select_related = ("user",)
    ordering = ("-created_at",)

    @admin.display(description="Total Items")
    def total_items_display(self, obj):
        return obj.total_items

    @admin.display(description="Total Price")
    def total_price_display(self, obj):
        return f"₹{obj.total_price}"


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ("cart", "product", "quantity", "total_price_display", "slug")
    search_fields = (
        "cart__user__username",
        "product__sku",
        "product__slug",
        "product__product__name",
        "slug",
    )
    autocomplete_fields = ("cart", "product")
    readonly_fields = ("slug", "total_price_display")
    list_select_related = ("cart", "cart__user", "product", "product__product")
    ordering = ("cart",)

    @admin.display(description="Total Price")
    def total_price_display(self, obj):
        return f"₹{obj.total_price}"