from rest_framework import serializers
from apps.products.models import (
    Category,
    Color,
    Product,
    ProductVariant,
    Stock,
    Review,
    ProductImage,
)


# =========================================================
# CATEGORY SERIALIZER
# =========================================================

class CategorySerializer(serializers.ModelSerializer):
    product_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "slug",
            "product_count",
        ]
        read_only_fields = [
            "id",
            "slug",
            "product_count",
        ]

    def get_product_count(self, obj):
        return obj.product.filter(is_active=True).count()


# =========================================================
# COLOR SERIALIZER
# =========================================================

class ColorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Color
        fields = [
            "id",
            "name",
            "hex_code",
            "slug",
        ]
        read_only_fields = [
            "id",
            "slug",
        ]


# =========================================================
# STOCK SERIALIZER
# =========================================================

class StockSerializer(serializers.ModelSerializer):
    available_quantity = serializers.IntegerField(read_only=True)

    class Meta:
        model = Stock
        fields = [
            "id",
            "variant",
            "quantity",
            "reserved_quantity",
            "available_quantity",
            "slug",
        ]
        read_only_fields = [
            "id",
            "slug",
            "available_quantity",
        ]


# =========================================================
# PRODUCT GALLERY IMAGE SERIALIZER
# =========================================================

class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = [
            "id",
            "product",
            "image",
            "alt_text",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
        ]


# =========================================================
# REVIEW SERIALIZER
# =========================================================

class ReviewSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    user_full_name = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = [
            "id",
            "user",
            "username",
            "user_full_name",
            "product",
            "rating",
            "image",
            "product_review",
            "slug",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "user",
            "username",
            "user_full_name",
            "slug",
            "created_at",
        ]

    def get_user_full_name(self, obj):
        if obj.user:
            full_name = f"{obj.user.first_name} {obj.user.last_name}".strip()
            return full_name if full_name else obj.user.username
        return "Anonymous"

    def validate_rating(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError("Rating must be between 1 and 5.")
        return value


# =========================================================
# PRODUCT VARIANT SERIALIZER
# =========================================================

class ProductVariantSerializer(serializers.ModelSerializer):
    name = serializers.CharField(read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    color_details = ColorSerializer(source="color", read_only=True)
    is_in_stock = serializers.BooleanField(read_only=True)
    stock_quantity = serializers.SerializerMethodField()

    class Meta:
        model = ProductVariant
        fields = [
            "id",
            "product",
            "product_name",
            "color",
            "color_details",
            "size",
            "sku",
            "slug",
            "price",
            "name",
            "is_active",
            "is_in_stock",
            "stock_quantity",
        ]
        read_only_fields = [
            "id",
            "slug",
            "name",
            "product_name",
            "color_details",
            "is_in_stock",
            "stock_quantity",
        ]

    def get_stock_quantity(self, obj):
        if hasattr(obj, "stock"):
            return obj.stock.available_quantity
        return 0


# =========================================================
# PRODUCT LIST SERIALIZER (OPTIMIZED FOR BROWSING / CATALOG)
# =========================================================

class ProductListSerializer(serializers.ModelSerializer):
    cat = CategorySerializer(many=True, read_only=True)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    min_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    max_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    in_stock = serializers.BooleanField(read_only=True)
    average_rating = serializers.FloatField(read_only=True)
    review_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "cat",
            "brand",
            "image",
            "price",
            "min_price",
            "max_price",
            "in_stock",
            "average_rating",
            "review_count",
            "is_active",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "slug",
            "price",
            "min_price",
            "max_price",
            "in_stock",
            "average_rating",
            "review_count",
            "created_at",
        ]


 

class ProductDetailSerializer(serializers.ModelSerializer):
    cat = CategorySerializer(many=True, read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    reviews = ReviewSerializer(many=True, read_only=True)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    min_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    max_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    in_stock = serializers.BooleanField(read_only=True)
    average_rating = serializers.FloatField(read_only=True)
    review_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "cat",
            "brand",
            "image",
            "description",
            "price",
            "min_price",
            "max_price",
            "in_stock",
            "average_rating",
            "review_count",
            "is_active",
            "created_at",
            "variants",
            "images",
            "reviews",
        ]
        read_only_fields = [
            "id",
            "slug",
            "price",
            "min_price",
            "max_price",
            "in_stock",
            "average_rating",
            "review_count",
            "created_at",
            "variants",
            "images",
            "reviews",
        ]


 
class ProductCreateUpdateSerializer(serializers.ModelSerializer):
    cat = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        many=True,
        required=False
    )
    is_active = serializers.BooleanField(default=True, required=False)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "cat",
            "brand",
            "image",
            "description",
            "is_active",
        ]
        read_only_fields = [
            "id",
            "slug",
        ]

    def to_internal_value(self, data):
        data = data.copy() if hasattr(data, "copy") else dict(data)

        # Resolve category inputs from cat_slug, category_slug, category, or cat
        cat_inputs = []
        for key in ["cat_slug", "category_slug", "category", "cat"]:
            if key in data:
                val = data.get(key)
                if isinstance(val, list):
                    cat_inputs.extend(val)
                elif val is not None and val != "":
                    cat_inputs.append(val)

        if cat_inputs:
            resolved_pks = []
            for item in cat_inputs:
                if item is None:
                    continue
                if isinstance(item, str) and "," in item:
                    sub_items = [s.strip() for s in item.split(",") if s.strip()]
                else:
                    sub_items = [item]

                for sub in sub_items:
                    if isinstance(sub, int) or (isinstance(sub, str) and sub.isdigit()):
                        pk = int(sub)
                        if Category.objects.filter(id=pk).exists():
                            resolved_pks.append(pk)
                        else:
                            raise serializers.ValidationError(
                                {"cat": f"Category with id '{pk}' does not exist."}
                            )
                    elif isinstance(sub, str) and sub.strip():
                        slug_val = sub.strip()
                        cat_obj = Category.objects.filter(slug=slug_val).first()
                        if not cat_obj:
                            cat_obj = Category.objects.filter(name__iexact=slug_val).first()
                        if cat_obj:
                            resolved_pks.append(cat_obj.id)
                        else:
                            raise serializers.ValidationError(
                                {"cat_slug": f"Category with slug or name '{slug_val}' does not exist."}
                            )
            data["cat"] = list(dict.fromkeys(resolved_pks))

        return super().to_internal_value(data)

    def validate_image(self, value):
        if value:
            from apps.products.validators import validate_uploaded_image
            is_valid, error = validate_uploaded_image(value)
            if not is_valid:
                raise serializers.ValidationError(error)
        return value


# Default ProductSerializer alias
ProductSerializer = ProductDetailSerializer
