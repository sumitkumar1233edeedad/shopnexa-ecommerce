from rest_framework import serializers
from apps.cart.models import Cart, CartItem
from apps.products.models import Product, ProductVariant


# =========================================================
# 1. CART ITEM SERIALIZER (FLATTENED ITEM + PRODUCT DETAILS)
# =========================================================

class CartItemSerializer(serializers.ModelSerializer):
    """
    Unified serializer for CartItem.
    Flattens product, variant, and color attributes directly into the item object.
    """
    product_name = serializers.CharField(source="product.product.name", read_only=True)
    product_slug = serializers.CharField(source="product.product.slug", read_only=True)
    brand = serializers.CharField(source="product.product.brand", read_only=True)
    variant_name = serializers.CharField(source="product.name", read_only=True)
    variant_slug = serializers.CharField(source="product.slug", read_only=True)
    color = serializers.CharField(source="product.color.name", read_only=True, default=None)
    color_hex = serializers.CharField(source="product.color.hex_code", read_only=True, default=None)
    size = serializers.CharField(source="product.size", read_only=True, default=None)
    price = serializers.DecimalField(source="product.price", max_digits=10, decimal_places=2, read_only=True)
    total_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    image = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = [
            "id",
            "slug",
            "quantity",
            "price",
            "total_price",
            "product_name",
            "product_slug",
            "variant_name",
            "variant_slug",
            "brand",
            "color",
            "color_hex",
            "size",
            "image",
        ]
        read_only_fields = fields

    def get_image(self, obj):
        img = getattr(obj.product.product, "image", None)
        if not img:
            return None
        request = self.context.get("request")
        if request:
            try:
                return request.build_absolute_uri(img.url)
            except Exception:
                pass
        return getattr(img, "url", None)


# =========================================================
# 2. CART SERIALIZER (FULL CART SUMMARY & ITEMS)
# =========================================================

class CartSerializer(serializers.ModelSerializer):
    """
    Full Cart serializer with nested items, count, and subtotal.
    """
    items = CartItemSerializer(many=True, read_only=True)
    total_items = serializers.IntegerField(read_only=True)
    total_price = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = Cart
        fields = [
            "id",
            "slug",
            "total_items",
            "total_price",
            "items",
            "created_at",
        ]
        read_only_fields = fields


# =========================================================
# 3. UNIFIED ACTION SERIALIZER (ADD / UPDATE / REMOVE)
# =========================================================

class CartActionSerializer(serializers.Serializer):
    """
    Single unified validator for all cart actions:
    - Add to cart: {"variant_slug": "iphone-16-black", "quantity": 1}
    - Update qty: {"action": "increase"} or {"action": "decrease"} or {"quantity": 3}
    """
    variant_slug = serializers.CharField(
        required=False,
        help_text="Variant slug (or Product slug fallback)"
    )
    quantity = serializers.IntegerField(
        default=1,
        min_value=1,
        required=False,
        help_text="Quantity (positive integer, min: 1)"
    )
    action = serializers.ChoiceField(
        choices=["increase", "decrease", "set"],
        required=False,
        help_text="Action to apply: 'increase', 'decrease', or 'set'"
    )

    def validate_variant_slug(self, value):
        variant = ProductVariant.objects.select_related(
            "product", "color", "stock"
        ).filter(slug=value, is_active=True).first()

        if not variant:
            product = Product.objects.filter(slug=value, is_active=True).first()
            if product and product.default_variant:
                variant = product.default_variant

        if not variant:
            raise serializers.ValidationError(
                f"Product or variant '{value}' does not exist or is inactive."
            )

        if hasattr(variant, "stock") and variant.stock:
            if variant.stock.available_quantity <= 0:
                raise serializers.ValidationError(
                    "This item is currently out of stock."
                )

        self.context["variant"] = variant
        return value
