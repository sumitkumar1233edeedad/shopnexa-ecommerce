from django.contrib import admin
from django.utils.html import format_html
from .models import Category, Color, Product, ProductVariant, Stock, Review, ProductImage


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name", "slug")
    readonly_fields = ("slug",)
    ordering = ("name",)


@admin.register(Color)
class ColorAdmin(admin.ModelAdmin):
    list_display = ("name", "color_preview", "hex_code", "slug")
    search_fields = ("name", "slug", "hex_code")
    readonly_fields = ("slug",)
    ordering = ("name",)

    @admin.display(description="Preview")
    def color_preview(self, obj):
        if obj.hex_code:
            return format_html(
                '<span style="display:inline-block; width:16px; height:16px; '
                'background-color:{}; border:1px solid #ccc; border-radius:3px; '
                'vertical-align:middle; margin-right:6px;"></span>{}',
                obj.hex_code,
                obj.hex_code,
            )
        return "-"


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 5
    fields = ("image", "alt_text", "created_at")
    readonly_fields = ("created_at",)


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    fields = ("color", "size", "sku", "slug", "price", "is_active")
    readonly_fields = ("slug",)
    autocomplete_fields = ("color",)
    extra = 0
    show_change_link = True


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "brand", "is_active", "price_display", "created_at", "slug")
    list_filter = ("is_active", "brand", "cat")
    search_fields = ("name", "slug", "brand", "description")
    filter_horizontal = ("cat",)
    readonly_fields = ("slug", "created_at", "price_display")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    inlines = [ProductVariantInline, ProductImageInline]

    @admin.display(description="Price")
    def price_display(self, obj):
        min_p = obj.min_price
        max_p = obj.max_price
        if min_p is not None and max_p is not None:
            if min_p == max_p:
                return f"₹{min_p}"
            return f"₹{min_p} - ₹{max_p}"
        return "-"


class StockInline(admin.StackedInline):
    model = Stock
    fields = ("quantity", "reserved_quantity", "available_stock_display", "slug")
    readonly_fields = ("available_stock_display", "slug")
    extra = 0

    @admin.display(description="Available Stock")
    def available_stock_display(self, obj):
        return obj.available_quantity if obj else 0


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ("product", "color", "size", "sku", "slug", "price", "is_active")
    list_filter = ("is_active", "color", "size")
    search_fields = ("product__name", "product__slug", "sku", "slug")
    autocomplete_fields = ("product", "color")
    readonly_fields = ("slug",)
    list_select_related = ("product", "color")
    ordering = ("product", "sku")
    inlines = [StockInline]


@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = ("variant", "quantity", "reserved_quantity", "available_stock_display", "slug")
    search_fields = ("variant__sku", "variant__slug", "variant__product__name", "slug")
    autocomplete_fields = ("variant",)
    readonly_fields = ("slug", "available_stock_display")
    list_select_related = ("variant", "variant__product")
    ordering = ("variant__sku",)

    @admin.display(description="Available Stock")
    def available_stock_display(self, obj):
        return obj.available_quantity


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("user", "product", "rating_stars", "created_at", "slug")
    list_filter = ("rating", "created_at")
    search_fields = ("user__username", "product__name", "product__slug", "product_review", "slug")
    autocomplete_fields = ("user", "product")
    readonly_fields = ("slug", "created_at")
    date_hierarchy = "created_at"
    list_select_related = ("user", "product")
    ordering = ("-created_at",)

    @admin.display(description="Rating")
    def rating_stars(self, obj):
        return f"{obj.rating} ★"
