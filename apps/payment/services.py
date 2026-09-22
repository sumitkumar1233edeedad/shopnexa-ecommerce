import logging
from decimal import Decimal
import razorpay
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from apps.payment.models import Payment
from apps.cart.models import Cart

logger = logging.getLogger(__name__)


def get_razorpay_client():
    """
    Initializes and returns the Razorpay Client instance with configured keys.
    """
    key_id = getattr(settings, "RAZORPAY_KEY_ID", "").strip()
    key_secret = getattr(settings, "RAZORPAY_KEY_SECRET", "").strip()
    if not key_id or not key_secret:
        raise ValueError("Razorpay API credentials (RAZORPAY_KEY_ID or RAZORPAY_KEY_SECRET) are missing.")
    return razorpay.Client(auth=(key_id, key_secret))


def create_razorpay_order(order):
    """
    Creates an order on Razorpay for the specified Django Order.
    Amount must be converted to the lowest currency unit (paise for INR).
    """
    client = get_razorpay_client()
    amount_in_paise = int(Decimal(str(order.total_amount)) * 100)

    order_payload = {
        "amount": amount_in_paise,
        "currency": getattr(settings, "RAZORPAY_CURRENCY", "INR"),
        "receipt": str(order.order_number)[:40],
        "payment_capture": 1,
        "notes": {
            "order_number": str(order.order_number),
            "order_slug": str(order.slug),
            "user_email": getattr(order.user, "email", ""),
        }
    }

    logger.info("Creating Razorpay order for #%s: %s paise", order.order_number, amount_in_paise)
    razorpay_order = client.order.create(data=order_payload)
    return razorpay_order


def verify_razorpay_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature):
    """
    Verifies the cryptographic HMAC SHA-256 signature returned by Razorpay checkout.
    Returns True if valid, False otherwise.
    """
    client = get_razorpay_client()
    params_dict = {
        "razorpay_order_id": str(razorpay_order_id).strip(),
        "razorpay_payment_id": str(razorpay_payment_id).strip(),
        "razorpay_signature": str(razorpay_signature).strip(),
    }
    try:
        client.utility.verify_payment_signature(params_dict)
        return True
    except razorpay.errors.SignatureVerificationError as e:
        logger.warning("Razorpay signature verification failed: %s", e)
        return False
    except Exception as e:
        logger.error("Unexpected error verifying Razorpay signature: %s", e)
        return False


def verify_razorpay_webhook_signature(body_bytes, signature):
    """
    Verifies the cryptographic signature of an incoming Razorpay webhook.
    """
    client = get_razorpay_client()
    webhook_secret = getattr(settings, "RAZORPAY_WEBHOOK_SECRET", "").strip()
    if not webhook_secret:
        logger.error("RAZORPAY_WEBHOOK_SECRET is not configured.")
        return False
    try:
        client.utility.verify_webhook_signature(body_bytes.decode("utf-8"), signature, webhook_secret)
        return True
    except Exception as e:
        logger.warning("Razorpay webhook signature verification failed: %s", e)
        return False


def complete_order_payment(order, transaction_id, gateway_order_id=None, gateway_signature=None, payment_method="online"):
    """
    Safely and atomically completes the payment for an order:
    1. Updates or creates Payment model record to 'completed'.
    2. Updates Order status to 'confirmed'.
    3. Deducts inventory stock for each ordered item.
    4. Records coupon usage if applied.
    5. Clears the user's active shopping cart.
    """
    with transaction.atomic():
        payment, created = Payment.objects.get_or_create(
            order=order,
            defaults={
                "user": order.user,
                "amount": order.total_amount,
                "payment_method": payment_method,
            }
        )

        payment.payment_method = payment_method
        payment.transaction_id = transaction_id
        if gateway_order_id:
            payment.gateway_order_id = gateway_order_id
        if transaction_id:
            payment.gateway_payment_id = transaction_id
        if gateway_signature:
            payment.gateway_signature = gateway_signature

        payment.status = "completed"
        payment.paid_at = timezone.now()
        payment.save()

        # Update order status
        order.status = "confirmed"
        order.save(update_fields=["status"])

        # Deduct inventory stock
        for item in order.items.select_related("variant").all():
            if hasattr(item.variant, "stock"):
                stock = item.variant.stock
                if stock.quantity >= item.quantity:
                    stock.quantity -= item.quantity
                    stock.save(update_fields=["quantity"])
                else:
                    # Deduct as much as available
                    stock.quantity = 0
                    stock.save(update_fields=["quantity"])

        # Record coupon usage
        if getattr(order, "coupon", None):
            try:
                from apps.coupons.services import record_coupon_usage
                record_coupon_usage(order, coupon=order.coupon, discount_amount=order.discount_amount)
            except Exception as e:
                logger.warning("Failed recording coupon usage for order #%s: %s", order.order_number, e)

        # Clear active shopping cart
        cart_obj = Cart.objects.filter(user=order.user).first()
        if cart_obj:
            cart_obj.items.all().delete()

        logger.info("Order #%s successfully completed and confirmed with TXN: %s", order.order_number, transaction_id)
        return payment
