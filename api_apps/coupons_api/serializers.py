import re
import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import serializers

from apps.coupons.models import Coupon, CouponConfiguration, CouponUsage
from apps.coupons.services import (
    can_user_use_coupon,
    get_available_coupons,
    get_best_coupon_for_user,
    get_user_weekly_coupon_info,
    get_user_weekly_coupon_usage,
    validate_coupon_for_user,
)

User = get_user_model()


# ==============================================================================
# 1. COUPON MINIMAL SERIALIZER (Lightweight representation for nested usage)
# ==============================================================================
class CouponMinimalSerializer(serializers.ModelSerializer):
    """
    Lightweight, read-only serializer for embedding inside cart, order,
    or compact UI lists.
    """
    discount_type_display = serializers.CharField(
        source="get_discount_type_display",
        read_only=True
    )
    status_display = serializers.CharField(read_only=True)

    class Meta:
        model = Coupon
        fields = [
            "id",
            "code",
            "slug",
            "discount_type",
            "discount_type_display",
            "discount_value",
            "minimum_order_amount",
            "maximum_discount_amount",
            "status_display",
            "is_active",
        ]
        read_only_fields = fields


# ==============================================================================
# 2. COUPON SERIALIZER (Standard Read / Public List & Detail with Context Awareness)
# ==============================================================================
class CouponSerializer(serializers.ModelSerializer):
    """
    Comprehensive read serializer for Coupons.
    Exposes model fields, computed properties, and dynamically annotates
    user qualification and discount estimations when request/cart context is present.
    """
    discount_type_display = serializers.CharField(
        source="get_discount_type_display",
        read_only=True
    )
    is_expired = serializers.BooleanField(read_only=True)
    is_upcoming = serializers.BooleanField(read_only=True)
    status_display = serializers.CharField(read_only=True)

    # Dynamic contextual fields (populated if cart_amount or request is in context)
    qualifies = serializers.SerializerMethodField()
    amount_needed = serializers.SerializerMethodField()
    estimated_discount = serializers.SerializerMethodField()
    user_usage_count = serializers.SerializerMethodField()
    user_remaining_uses = serializers.SerializerMethodField()
    can_use_now = serializers.SerializerMethodField()

    class Meta:
        model = Coupon
        fields = [
            "id",
            "code",
            "slug",
            "description",
            "discount_type",
            "discount_type_display",
            "discount_value",
            "minimum_order_amount",
            "maximum_discount_amount",
            "valid_from",
            "valid_until",
            "usage_limit",
            "used_count",
            "per_user_limit",
            "weekly_user_limit",
            "is_active",
            "is_expired",
            "is_upcoming",
            "status_display",
            "qualifies",
            "amount_needed",
            "estimated_discount",
            "user_usage_count",
            "user_remaining_uses",
            "can_use_now",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def _get_cart_amount(self):
        """Helper to extract cart/order amount from context."""
        context = self.context or {}
        if "cart_amount" in context and context["cart_amount"] is not None:
            try:
                return Decimal(str(context["cart_amount"]))
            except Exception:
                return Decimal("0.00")
        if "order_amount" in context and context["order_amount"] is not None:
            try:
                return Decimal(str(context["order_amount"]))
            except Exception:
                return Decimal("0.00")
        return None

    def _get_user(self):
        """Helper to extract authenticated user from context."""
        context = self.context or {}
        request = context.get("request")
        if request and hasattr(request, "user") and request.user.is_authenticated:
            return request.user
        user = context.get("user")
        if user and getattr(user, "is_authenticated", False):
            return user
        return None

    def get_qualifies(self, obj):
        # If pre-annotated by get_available_coupons
        if hasattr(obj, "qualifies"):
            return obj.qualifies
        cart_amount = self._get_cart_amount()
        if cart_amount is not None:
            return cart_amount >= obj.minimum_order_amount
        return None

    def get_amount_needed(self, obj):
        if hasattr(obj, "amount_needed"):
            return obj.amount_needed
        cart_amount = self._get_cart_amount()
        if cart_amount is not None:
            return max(Decimal("0.00"), obj.minimum_order_amount - cart_amount)
        return None

    def get_estimated_discount(self, obj):
        if hasattr(obj, "estimated_discount"):
            return obj.estimated_discount
        cart_amount = self._get_cart_amount()
        if cart_amount is not None:
            if cart_amount >= obj.minimum_order_amount:
                return obj.calculate_discount(cart_amount)
            return Decimal("0.00")
        return None

    def get_user_usage_count(self, obj):
        user = self._get_user()
        if not user:
            return None
        return CouponUsage.objects.filter(coupon=obj, user=user).count()

    def get_user_remaining_uses(self, obj):
        user = self._get_user()
        if not user or obj.per_user_limit is None:
            return obj.per_user_limit
        used = CouponUsage.objects.filter(coupon=obj, user=user).count()
        return max(0, obj.per_user_limit - used)

    def get_can_use_now(self, obj):
        is_valid, _ = obj.is_valid_now()
        if not is_valid:
            return False
        user = self._get_user()
        if user:
            can_weekly, _ = can_user_use_coupon(user, coupon=obj)
            if not can_weekly:
                return False
            if obj.per_user_limit is not None:
                used = CouponUsage.objects.filter(coupon=obj, user=user).count()
                if used >= obj.per_user_limit:
                    return False
        return True


# ==============================================================================
# 3. COUPON CREATE & UPDATE SERIALIZER (Admin / Management with Full Validation)
# ==============================================================================
class CouponCreateUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating and updating Coupons with comprehensive validation
    matching the domain rules (uppercase code, dates, percentage caps, minimum amounts).
    """
    code = serializers.CharField(
        max_length=50,
        help_text="Unique coupon code (alphanumeric, uppercase, dashes, underscores)."
    )
    discount_type = serializers.ChoiceField(
        choices=Coupon.DISCOUNT_TYPE_CHOICES,
        default="percentage"
    )
    discount_value = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.01")
    )
    minimum_order_amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        min_value=Decimal("0.00")
    )
    maximum_discount_amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        allow_null=True,
        min_value=Decimal("0.01")
    )
    valid_from = serializers.DateTimeField(
        default=timezone.now
    )
    valid_until = serializers.DateTimeField()
    usage_limit = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1
    )
    per_user_limit = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1
    )
    weekly_user_limit = serializers.IntegerField(
        default=5,
        min_value=1
    )

    class Meta:
        model = Coupon
        fields = [
            "id",
            "code",
            "slug",
            "description",
            "discount_type",
            "discount_value",
            "minimum_order_amount",
            "maximum_discount_amount",
            "valid_from",
            "valid_until",
            "usage_limit",
            "used_count",
            "per_user_limit",
            "weekly_user_limit",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "slug", "used_count", "created_at", "updated_at"]

    def validate_code(self, value):
        code = value.strip().upper()
        if not code:
            raise serializers.ValidationError("Coupon code cannot be empty.")

        # Pattern check: alphanumeric, underscores, hyphens
        if not re.match(r"^[A-Z0-9_\-]+$", code):
            raise serializers.ValidationError(
                "Coupon code may only contain uppercase letters, numbers, hyphens, and underscores."
            )

        # Uniqueness check (case-insensitive)
        qs = Coupon.objects.filter(code__iexact=code)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(f"A coupon with code '{code}' already exists.")

        return code

    def validate_discount_value(self, value):
        if value <= Decimal("0.00"):
            raise serializers.ValidationError("Discount value must be greater than zero.")
        return value

    def validate(self, attrs):
        discount_type = attrs.get(
            "discount_type",
            self.instance.discount_type if self.instance else "percentage"
        )
        discount_value = attrs.get(
            "discount_value",
            self.instance.discount_value if self.instance else None
        )

        # Percentage cannot exceed 100%
        if discount_type == "percentage" and discount_value is not None and discount_value > Decimal("100.00"):
            raise serializers.ValidationError({
                "discount_value": "Percentage discount cannot exceed 100%."
            })

        # Date range validation
        valid_from = attrs.get(
            "valid_from",
            self.instance.valid_from if self.instance else timezone.now()
        )
        valid_until = attrs.get(
            "valid_until",
            self.instance.valid_until if self.instance else None
        )

        if valid_from and valid_until and valid_until <= valid_from:
            raise serializers.ValidationError({
                "valid_until": "End date/time must be after start date/time."
            })

        return attrs

    def create(self, validated_data):
        validated_data["code"] = validated_data["code"].strip().upper()
        if not validated_data.get("slug"):
            base_slug = slugify(validated_data["code"])
            slug = base_slug
            if Coupon.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{uuid.uuid4().hex[:6]}"
            validated_data["slug"] = slug
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if "code" in validated_data:
            validated_data["code"] = validated_data["code"].strip().upper()
        return super().update(instance, validated_data)


# ==============================================================================
# 4. COUPON APPLY SERIALIZER (Input validator for applying coupon at checkout)
# ==============================================================================
class CouponApplySerializer(serializers.Serializer):
    """
    Action serializer for cart/checkout coupon submission.
    Accepts coupon code or auto_apply flag, along with optional order_amount.
    """
    code = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=50,
        help_text="Coupon code to apply (e.g. SAVE20). Optional if auto_apply is True."
    )
    coupon_code = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=50,
        write_only=True,
        help_text="Alias for 'code'."
    )
    order_amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        min_value=Decimal("0.00"),
        help_text="Order/cart subtotal. If omitted, calculated from user's active cart."
    )
    auto_apply = serializers.BooleanField(
        default=False,
        help_text="If True, automatically discovers and applies the best qualifying coupon."
    )

    def validate(self, attrs):
        code = (attrs.get("code") or attrs.get("coupon_code") or "").strip().upper()
        auto_apply = attrs.get("auto_apply", False) or (code == "AUTO")

        if auto_apply:
            attrs["auto_apply"] = True
            attrs["code"] = ""
        else:
            if not code:
                raise serializers.ValidationError({
                    "code": "Please enter a coupon code or enable auto-apply."
                })
            attrs["code"] = code

        # Clean alias
        attrs.pop("coupon_code", None)
        return attrs


# ==============================================================================
# 5. COUPON VALIDATION RESULT SERIALIZER (Output response for apply/verify actions)
# ==============================================================================
class CouponValidationResultSerializer(serializers.Serializer):
    """
    Standardized response serializer returned when applying or testing a coupon.
    Provides clear validation status, calculated discount, and financial breakdown.
    """
    is_valid = serializers.BooleanField()
    message = serializers.CharField()
    coupon = CouponMinimalSerializer(allow_null=True, required=False)
    order_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    discount_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    final_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    weekly_info = serializers.DictField(required=False, allow_null=True)


# ==============================================================================
# 6. COUPON USAGE SERIALIZER (Tracks usage history per user/order)
# ==============================================================================
class CouponUsageSerializer(serializers.ModelSerializer):
    """
    Read-only serializer for recording and inspecting historical coupon usage.
    """
    coupon_code = serializers.CharField(source="coupon.code", read_only=True)
    coupon_discount_type = serializers.CharField(source="coupon.discount_type", read_only=True)
    coupon_discount_value = serializers.DecimalField(
        source="coupon.discount_value",
        max_digits=10,
        decimal_places=2,
        read_only=True
    )
    username = serializers.CharField(source="user.username", read_only=True)
    user_email = serializers.CharField(source="user.email", read_only=True)
    order_number = serializers.SerializerMethodField()
    order_slug = serializers.SerializerMethodField()

    class Meta:
        model = CouponUsage
        fields = [
            "id",
            "slug",
            "coupon",
            "coupon_code",
            "coupon_discount_type",
            "coupon_discount_value",
            "user",
            "username",
            "user_email",
            "order",
            "order_number",
            "order_slug",
            "discount_amount",
            "used_at",
        ]
        read_only_fields = fields

    def get_order_number(self, obj):
        return getattr(obj.order, "order_number", None) if obj.order else None

    def get_order_slug(self, obj):
        return getattr(obj.order, "slug", None) if obj.order else None


# ==============================================================================
# 7. COUPON CONFIGURATION SERIALIZER (Global Settings Singleton)
# ==============================================================================
class CouponConfigurationSerializer(serializers.ModelSerializer):
    """
    Serializer for managing store-wide coupon configuration (singleton).
    """
    weekly_user_limit = serializers.IntegerField(
        min_value=1,
        help_text="Global maximum successful coupon uses allowed per user per week."
    )

    class Meta:
        model = CouponConfiguration
        fields = [
            "id",
            "weekly_user_limit",
            "updated_at",
        ]
        read_only_fields = ["id", "updated_at"]

    def update(self, instance, validated_data):
        instance.weekly_user_limit = validated_data.get(
            "weekly_user_limit",
            instance.weekly_user_limit
        )
        instance.save()
        return instance


# ==============================================================================
# 8. USER WEEKLY COUPON STATS SERIALIZER (Customer UI & Checkout Status)
# ==============================================================================
class UserWeeklyCouponInfoSerializer(serializers.Serializer):
    """
    Output serializer for the authenticated user's weekly coupon usage status.
    """
    usage_count = serializers.IntegerField(
        help_text="Number of coupons used by user in current week (Mon-Sun)."
    )
    weekly_limit = serializers.IntegerField(
        help_text="Weekly coupon usage cap for user."
    )
    remaining = serializers.IntegerField(
        help_text="Remaining coupon uses available this week."
    )
    is_limit_reached = serializers.BooleanField(
        help_text="True if user has reached their weekly limit."
    )
