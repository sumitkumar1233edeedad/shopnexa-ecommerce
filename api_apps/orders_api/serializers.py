import uuid
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers

from apps.accounts.models import Address
from apps.cart.models import Cart
from apps.order.models import Order, OrderItem
from apps.payment.models import Payment

try:
    from apps.coupons.services import validate_coupon_for_user, record_coupon_usage
except ImportError:
    validate_coupon_for_user = None
    record_coupon_usage = None


# ============================================================
# 1. ORDER ITEM SERIALIZER (Line items in an order)
# ============================================================
class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="variant.product.name", read_only=True)
    variant_name = serializers.CharField(source="variant.name", read_only=True, default=None)
    sku = serializers.CharField(source="variant.sku", read_only=True)
    color = serializers.CharField(source="variant.color.name", read_only=True, default=None)
    size = serializers.CharField(source="variant.size", read_only=True, default=None)
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    image = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = [
            "id",
            "slug",
            "variant",
            "product_name",
            "variant_name",
            "sku",
            "color",
            "size",
            "quantity",
            "price",
            "subtotal",
            "image",
        ]
        read_only_fields = ["id", "slug", "price", "subtotal"]

    def get_image(self, obj):
        img = None
        if hasattr(obj.variant, "product") and getattr(obj.variant.product, "image", None):
            img = obj.variant.product.image
        if not img:
            return None
        request = self.context.get("request")
        if request:
            try:
                return request.build_absolute_uri(img.url)
            except Exception:
                pass
        return getattr(img, "url", None)


# ============================================================
# 2. ORDER OUTPUT SERIALIZER (Full Order representation)
# ============================================================
class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    coupon_code = serializers.CharField(source="coupon.code", read_only=True, default=None)
    total_items = serializers.IntegerField(read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "slug",
            "status",
            "status_display",
            "total_amount",
            "discount_amount",
            "coupon_code",
            "shipping_name",
            "shipping_phone",
            "shipping_city",
            "shipping_pincode",
            "shipping_address",
            "total_items",
            "items",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "order_number",
            "slug",
            "status",
            "status_display",
            "total_amount",
            "discount_amount",
            "coupon_code",
            "total_items",
            "created_at",
            "updated_at",
        ]


# ============================================================
# 3. ORDER CREATE SERIALIZER (Checkout & Place Order Validator)
# ============================================================
class OrderCreateSerializer(serializers.Serializer):
    address_id = serializers.CharField(required=False, allow_blank=True, default=None)
    address_slug = serializers.CharField(required=False, allow_blank=True, default=None)
    shipping_name = serializers.CharField(required=False, allow_blank=True, max_length=100)
    shipping_phone = serializers.CharField(required=False, allow_blank=True, max_length=20)
    shipping_city = serializers.CharField(required=False, allow_blank=True, max_length=100)
    shipping_pincode = serializers.CharField(required=False, allow_blank=True, max_length=10)
    shipping_address = serializers.CharField(required=False, allow_blank=True)
    save_address = serializers.BooleanField(required=False, default=False)
    coupon_code = serializers.CharField(required=False, allow_blank=True, default="")
    payment_method = serializers.ChoiceField(
        choices=["cod", "online", "razorpay", "upi", "card", "netbanking"],
        default="cod",
    )

    def validate(self, attrs):
        request = self.context.get("request")
        if not request or not request.user or not request.user.is_authenticated:
            raise serializers.ValidationError("Authentication is required to place an order.")

        # 1. Validate Cart
        cart = Cart.objects.filter(user=request.user).first()
        if not cart or not cart.items.exists():
            raise serializers.ValidationError("Your cart is empty. Please add items before checking out.")

        cart_items = cart.items.select_related(
            "product__product", "product__color", "product__stock"
        ).all()

        if not cart_items.exists():
            raise serializers.ValidationError("Your cart is empty.")

        # 2. Check stock availability
        for item in cart_items:
            variant = item.product
            if hasattr(variant, "stock") and variant.stock:
                if variant.stock.quantity < item.quantity:
                    raise serializers.ValidationError(
                        f"Insufficient stock for {variant.product.name} (SKU: {variant.sku}). Available: {variant.stock.quantity}"
                    )

        # 3. Validate shipping details (either address_id or manual inputs)
        addr_id = attrs.get("address_id") or attrs.get("address_slug")
        if addr_id:
            addr_q = Q(slug=str(addr_id))
            if str(addr_id).isdigit():
                addr_q |= Q(id=int(addr_id))

            saved_addr = Address.objects.filter(addr_q, user=request.user).first()
            if not saved_addr:
                raise serializers.ValidationError({"address_id": "Selected address not found."})

            attrs["shipping_name"] = saved_addr.name
            attrs["shipping_phone"] = saved_addr.phone or ""
            attrs["shipping_city"] = saved_addr.city
            attrs["shipping_pincode"] = saved_addr.pincode
            full_addr = f"{saved_addr.address_line}, {saved_addr.locality or ''}, {saved_addr.city}, {saved_addr.state} - {saved_addr.pincode}"
            attrs["shipping_address"] = full_addr.replace(", ,", ",").replace(" ,", ",").strip()
        else:
            name = (attrs.get("shipping_name") or "").strip()
            phone = (attrs.get("shipping_phone") or "").strip()
            city = (attrs.get("shipping_city") or "").strip()
            pincode = (attrs.get("shipping_pincode") or "").strip()
            address = (attrs.get("shipping_address") or "").strip()

            if not (name and phone and city and pincode and address):
                raise serializers.ValidationError(
                    "Shipping details required: shipping_name, shipping_phone, shipping_city, shipping_pincode, and shipping_address (or provide address_id)."
                )

        # 4. Coupon validation
        subtotal = sum(item.total_price for item in cart_items)
        coupon_code = (attrs.get("coupon_code") or "").strip() or request.session.get("applied_coupon_code", "")
        applied_coupon = None
        discount_amount = Decimal("0.00")

        if coupon_code and validate_coupon_for_user:
            is_valid, error_msg, coupon_obj, discount = validate_coupon_for_user(
                coupon_code, request.user, Decimal(str(subtotal))
            )
            if is_valid:
                applied_coupon = coupon_obj
                discount_amount = discount
            else:
                raise serializers.ValidationError({"coupon_code": f"Coupon error: {error_msg}"})

        attrs["cart"] = cart
        attrs["cart_items"] = cart_items
        attrs["subtotal"] = subtotal
        attrs["applied_coupon"] = applied_coupon
        attrs["discount_amount"] = discount_amount
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        user = request.user
        cart = validated_data["cart"]
        cart_items = validated_data["cart_items"]
        subtotal = validated_data["subtotal"]
        applied_coupon = validated_data["applied_coupon"]
        discount_amount = validated_data["discount_amount"]
        payment_method = validated_data.get("payment_method", "cod")

        discounted_subtotal = max(Decimal("0.00"), Decimal(str(subtotal)) - discount_amount)
        shipping_fee = Decimal("0.00") if subtotal >= 500 else Decimal("50.00")
        grand_total = discounted_subtotal + shipping_fee

        is_online = payment_method != "cod"
        order_status = "pending_payment" if is_online else "pending"

        with transaction.atomic():
            timestamp = timezone.now().strftime("%Y%m%d%H%M")
            order_number = f"ORD-{timestamp}-{uuid.uuid4().hex[:6].upper()}"

            order = Order.objects.create(
                user=user,
                order_number=order_number,
                status=order_status,
                total_amount=grand_total,
                coupon=applied_coupon,
                discount_amount=discount_amount,
                shipping_name=validated_data["shipping_name"],
                shipping_phone=validated_data["shipping_phone"],
                shipping_city=validated_data["shipping_city"],
                shipping_pincode=validated_data["shipping_pincode"],
                shipping_address=validated_data["shipping_address"],
            )

            # Create Order Items & deduct stock if COD
            for item in cart_items:
                OrderItem.objects.create(
                    order=order,
                    variant=item.product,
                    quantity=item.quantity,
                    price=item.product.price,
                )
                if not is_online and hasattr(item.product, "stock") and item.product.stock:
                    stock = item.product.stock
                    if stock.quantity >= item.quantity:
                        stock.quantity -= item.quantity
                        stock.save(update_fields=["quantity"])

            # Create Payment record
            Payment.objects.create(
                user=user,
                order=order,
                payment_method=payment_method,
                amount=grand_total,
                status="pending",
            )

            # Record coupon usage
            if applied_coupon and record_coupon_usage:
                record_coupon_usage(order, coupon=applied_coupon, discount_amount=discount_amount)

            # Clear session coupon & cart
            request.session.pop("applied_coupon_code", None)
            cart.items.all().delete()

        return order
