import logging
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers

from apps.order.models import Order
from apps.payment.models import Payment

try:
    from apps.payment.services import (
        complete_order_payment,
        create_razorpay_order,
        verify_razorpay_signature,
    )
except ImportError:
    complete_order_payment = None
    create_razorpay_order = None
    verify_razorpay_signature = None

User = get_user_model()
logger = logging.getLogger(__name__)


# ==============================================================================
# 1. PAYMENT MINIMAL SERIALIZER (Nested representation for Orders & Lists)
# ==============================================================================
class PaymentMinimalSerializer(serializers.ModelSerializer):
    """
    Lightweight, read-only serializer for embedding inside OrderSerializer
    or compact order history listings.
    """
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    payment_method_display = serializers.CharField(source="get_payment_method_display", read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id",
            "slug",
            "payment_method",
            "payment_method_display",
            "amount",
            "currency",
            "status",
            "status_display",
            "transaction_id",
            "paid_at",
            "created_at",
        ]
        read_only_fields = fields


# ==============================================================================
# 2. PAYMENT DETAIL SERIALIZER (Full Read Representation)
# ==============================================================================
class PaymentSerializer(serializers.ModelSerializer):
    """
    Detailed read serializer for Payment records.
    Exposes order reference details, customer information, status displays,
    and gateway transaction metadata (excluding sensitive signatures).
    """
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    payment_method_display = serializers.CharField(source="get_payment_method_display", read_only=True)
    order_number = serializers.CharField(source="order.order_number", read_only=True)
    order_slug = serializers.CharField(source="order.slug", read_only=True)
    user_email = serializers.CharField(source="user.email", read_only=True)
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = [
            "id",
            "slug",
            "order",
            "order_number",
            "order_slug",
            "user",
            "user_email",
            "user_name",
            "payment_method",
            "payment_method_display",
            "transaction_id",
            "gateway_order_id",
            "gateway_payment_id",
            "currency",
            "amount",
            "status",
            "status_display",
            "paid_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "slug",
            "order_number",
            "order_slug",
            "user_email",
            "user_name",
            "status_display",
            "payment_method_display",
            "paid_at",
            "created_at",
            "updated_at",
        ]

    def get_user_name(self, obj):
        if not obj.user:
            return None
        return obj.user.get_full_name() or obj.user.username


# ==============================================================================
# 3. PAYMENT INITIATE SERIALIZER (Checkout / Payment Gateway Initialization)
# ==============================================================================
class PaymentInitiateSerializer(serializers.Serializer):
    """
    Action serializer to initiate payment for an order.
    Validates that:
    1. The order exists and belongs to the authenticated user.
    2. The order is eligible for payment (not already paid/confirmed/cancelled).
    3. If payment_method is an online gateway (e.g. 'razorpay' or 'online'),
       it generates a Razorpay Order ID and returns the required checkout config.
    """
    order_slug = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Slug of the order to pay for."
    )
    order_number = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Order number of the order to pay for."
    )
    payment_method = serializers.ChoiceField(
        choices=Payment.PAYMENT_METHOD,
        default="online",
        help_text="Selected payment method."
    )

    def validate(self, attrs):
        request = self.context.get("request")
        if not request or not request.user or not request.user.is_authenticated:
            raise serializers.ValidationError("Authentication required to initiate payment.")

        order_slug = (attrs.get("order_slug") or "").strip()
        order_number = (attrs.get("order_number") or "").strip()

        if not order_slug and not order_number:
            raise serializers.ValidationError("Either 'order_slug' or 'order_number' must be provided.")

        order_qs = Order.objects.filter(user=request.user)
        if order_slug:
            order = order_qs.filter(slug=order_slug).first()
        else:
            order = order_qs.filter(order_number=order_number).first()

        if not order:
            raise serializers.ValidationError("Order not found or does not belong to you.")

        # Check order eligibility
        if order.status == "confirmed":
            raise serializers.ValidationError("This order has already been paid and confirmed.")
        if order.status == "cancelled":
            raise serializers.ValidationError("This order has been cancelled and cannot be paid.")

        attrs["order"] = order
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        order = validated_data["order"]
        payment_method = validated_data.get("payment_method", "online")

        # Get or create existing payment for this order
        payment, created = Payment.objects.get_or_create(
            order=order,
            defaults={
                "user": request.user,
                "amount": order.total_amount,
                "payment_method": payment_method,
                "status": "pending",
            },
        )

        # Update payment method and amount if needed
        if payment.payment_method != payment_method or payment.amount != order.total_amount:
            payment.payment_method = payment_method
            payment.amount = order.total_amount
            payment.save(update_fields=["payment_method", "amount"])

        razorpay_order_id = payment.gateway_order_id
        amount_in_paise = int(Decimal(str(order.total_amount)) * 100)

        # If online payment and no razorpay order id yet, generate one
        if payment_method in ["online", "razorpay", "upi", "card", "netbanking"] and create_razorpay_order:
            if not razorpay_order_id:
                try:
                    rzp_order = create_razorpay_order(order)
                    razorpay_order_id = rzp_order.get("id")
                    payment.gateway_order_id = razorpay_order_id
                    payment.save(update_fields=["gateway_order_id"])
                except Exception as e:
                    logger.error("Failed to initialize Razorpay order for #%s: %s", order.order_number, e)
                    raise serializers.ValidationError(
                        f"Failed to initiate payment gateway order: {str(e)}"
                    )

        return {
            "payment": payment,
            "order_number": order.order_number,
            "order_slug": order.slug,
            "amount": order.total_amount,
            "amount_in_paise": amount_in_paise,
            "currency": payment.currency or getattr(settings, "RAZORPAY_CURRENCY", "INR"),
            "payment_method": payment_method,
            "razorpay_key_id": getattr(settings, "RAZORPAY_KEY_ID", ""),
            "razorpay_order_id": razorpay_order_id,
            "user_name": order.shipping_name or request.user.get_full_name() or request.user.username,
            "user_email": getattr(request.user, "email", ""),
            "user_phone": order.shipping_phone or getattr(request.user, "phone", ""),
        }


# ==============================================================================
# 4. PAYMENT VERIFY SERIALIZER (Razorpay Signature Verification & Order Confirm)
# ==============================================================================
class PaymentVerifySerializer(serializers.Serializer):
    """
    Action serializer for verifying Razorpay checkout response.
    Validates HMAC SHA-256 signature and completes the order atomically.
    """
    order_slug = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Slug of the order being paid."
    )
    payment_slug = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Slug of the payment record (optional alternative to order_slug)."
    )
    razorpay_order_id = serializers.CharField(
        max_length=255,
        help_text="Order ID returned by Razorpay."
    )
    razorpay_payment_id = serializers.CharField(
        max_length=255,
        help_text="Payment ID / Transaction ID returned by Razorpay."
    )
    razorpay_signature = serializers.CharField(
        help_text="Cryptographic signature from Razorpay checkout."
    )

    def validate(self, attrs):
        request = self.context.get("request")
        if not request or not request.user or not request.user.is_authenticated:
            raise serializers.ValidationError("Authentication required.")

        order_slug = (attrs.get("order_slug") or "").strip()
        payment_slug = (attrs.get("payment_slug") or "").strip()

        order = None
        if order_slug:
            order = Order.objects.filter(slug=order_slug, user=request.user).first()
        elif payment_slug:
            payment = Payment.objects.filter(slug=payment_slug, user=request.user).select_related("order").first()
            if payment:
                order = payment.order

        if not order:
            raise serializers.ValidationError("Valid order not found for this payment verification.")

        attrs["order"] = order

        # Verify signature
        if verify_razorpay_signature:
            is_valid = verify_razorpay_signature(
                razorpay_order_id=attrs["razorpay_order_id"],
                razorpay_payment_id=attrs["razorpay_payment_id"],
                razorpay_signature=attrs["razorpay_signature"],
            )
            if not is_valid:
                # Mark payment as failed if instance exists
                payment = getattr(order, "payment", None)
                if payment:
                    payment.status = "failed"
                    payment.save(update_fields=["status"])
                raise serializers.ValidationError({
                    "razorpay_signature": "Signature verification failed. Payment cannot be verified."
                })
        else:
            raise serializers.ValidationError("Payment verification service unavailable.")

        return attrs

    def save(self):
        order = self.validated_data["order"]
        razorpay_payment_id = self.validated_data["razorpay_payment_id"]
        razorpay_order_id = self.validated_data["razorpay_order_id"]
        razorpay_signature = self.validated_data["razorpay_signature"]

        if not complete_order_payment:
            raise serializers.ValidationError("Order completion service unavailable.")

        payment = complete_order_payment(
            order=order,
            transaction_id=razorpay_payment_id,
            gateway_order_id=razorpay_order_id,
            gateway_signature=razorpay_signature,
            payment_method="online",
        )
        return payment


# ==============================================================================
# 5. PAYMENT STATUS UPDATE SERIALIZER (Admin / Management)
# ==============================================================================
class PaymentStatusUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for staff/admin to manually update payment status or transaction details.
    """
    status = serializers.ChoiceField(choices=Payment.PAYMENT_STATUS)
    transaction_id = serializers.CharField(required=False, allow_blank=True, max_length=255)

    class Meta:
        model = Payment
        fields = [
            "status",
            "transaction_id",
            "paid_at",
        ]

    def update(self, instance, validated_data):
        new_status = validated_data.get("status", instance.status)
        instance.status = new_status

        if "transaction_id" in validated_data:
            instance.transaction_id = validated_data["transaction_id"]

        if new_status == "completed" and not instance.paid_at:
            instance.paid_at = timezone.now()
            # Also ensure the linked order is confirmed
            if instance.order and instance.order.status != "confirmed":
                instance.order.status = "confirmed"
                instance.order.save(update_fields=["status"])
        elif new_status in ["failed", "refunded"]:
            if "paid_at" in validated_data:
                instance.paid_at = validated_data["paid_at"]

        instance.save()
        return instance


# ==============================================================================
# 6. PAYMENT REFUND SERIALIZER (Staff / Admin Action)
# ==============================================================================
class PaymentRefundSerializer(serializers.Serializer):
    """
    Serializer for initiating or recording a refund on a completed payment.
    """
    refund_amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        min_value=Decimal("0.01"),
        help_text="Amount to refund. Defaults to the full payment amount if not specified."
    )
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=255,
        help_text="Reason for refund."
    )

    def validate(self, attrs):
        payment = self.context.get("payment")
        if not payment:
            raise serializers.ValidationError("Payment context is required.")

        if payment.status != "completed":
            raise serializers.ValidationError(
                f"Cannot refund a payment with status '{payment.status}'. Only completed payments can be refunded."
            )

        refund_amount = attrs.get("refund_amount")
        if refund_amount is not None and refund_amount > payment.amount:
            raise serializers.ValidationError({
                "refund_amount": f"Refund amount cannot exceed total payment amount of {payment.currency} {payment.amount}."
            })

        attrs["refund_amount"] = refund_amount or payment.amount
        return attrs
