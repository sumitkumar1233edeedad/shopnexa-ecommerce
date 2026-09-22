from django.contrib import admin
from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    fields = ("variant", "quantity", "price", "subtotal_display", "slug")
    readonly_fields = ("subtotal_display", "slug")
    autocomplete_fields = ("variant",)
    extra = 0
    show_change_link = True

    @admin.display(description="Subtotal")
    def subtotal_display(self, obj):
        return f"₹{obj.subtotal}" if obj and obj.pk else "-"


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_number",
        "slug",
        "user",
        "status",
        "total_amount",
        "total_items_display",
        "created_at",
        "updated_at",
    )
    list_filter = ("status", "created_at")
    search_fields = (
        "order_number",
        "slug",
        "user__username",
        "user__email",
        "shipping_name",
        "shipping_phone",
        "shipping_city",
        "shipping_pincode",
    )
    readonly_fields = ("order_number", "slug", "created_at", "updated_at", "total_items_display")
    autocomplete_fields = ("user",)
    date_hierarchy = "created_at"
    inlines = [OrderItemInline]
    list_select_related = ("user",)
    ordering = ("-created_at",)

    @admin.display(description="Total Items")
    def total_items_display(self, obj):
        return obj.total_items


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "variant", "quantity", "price", "subtotal_display", "slug")
    search_fields = (
        "order__order_number",
        "order__slug",
        "variant__sku",
        "variant__slug",
        "variant__product__name",
        "slug",
    )
    autocomplete_fields = ("order", "variant")
    readonly_fields = ("slug", "subtotal_display")
    list_select_related = ("order", "variant", "variant__product")
    ordering = ("order",)

    @admin.display(description="Subtotal")
    def subtotal_display(self, obj):
        return f"₹{obj.subtotal}"
