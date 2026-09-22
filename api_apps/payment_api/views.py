import json
import logging
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.order.models import Order
from apps.payment.models import Payment
from apps.payment.services import (
    complete_order_payment,
    create_razorpay_order,
    verify_razorpay_signature,
    verify_razorpay_webhook_signature,
)
from .serializers import (
    PaymentInitiateSerializer,
    PaymentMinimalSerializer,
    PaymentSerializer,
    PaymentVerifySerializer,
)

logger = logging.getLogger(__name__)


# ==============================================================================
# 1. PAYMENT PROCESS / INITIATE API VIEW (Replaces payment_process)
# ==============================================================================
class PaymentProcessAPIView(APIView):
    """
    GET /api/payments/process/<order_slug>/
    POST /api/payments/process/<order_slug>/

    Initiates or retrieves payment details for an order.
    Generates a Razorpay Order ID if not already generated,
    and returns all required parameters for frontend Razorpay checkout.
    Uses transaction.atomic to safely get/update payment records.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, order_slug):
        return self._handle_process(request, order_slug)

    def post(self, request, order_slug):
        return self._handle_process(request, order_slug)

    def _handle_process(self, request, order_slug):
        order = (
            Order.objects.prefetch_related(
                "items__variant__product",
                "items__variant__color"
            )
            .filter(slug=order_slug, user=request.user)
            .first()
        )

        if not order:
            return Response(
                {"success": False, "error": "Order not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if already paid/confirmed
        if order.status == "confirmed":
            return Response(
                {
                    "success": False,
                    "is_already_paid": True,
                    "message": "This order has already been paid and confirmed.",
                    "order_number": order.order_number,
                    "order_slug": order.slug,
                    "status": order.status,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        payment_method = request.data.get("payment_method", "online") if request.method == "POST" else "online"

        # Atomically get or create Payment record to prevent race conditions
        with transaction.atomic():
            payment, created = Payment.objects.select_for_update().get_or_create(
                order=order,
                defaults={
                    "user": request.user,
                    "amount": order.total_amount,
                    "payment_method": payment_method,
                    "status": "pending",
                },
            )

            # Ensure payment_method is updated if changed
            if payment.payment_method != payment_method:
                payment.payment_method = payment_method
                payment.save(update_fields=["payment_method"])

        # Generate or reuse Razorpay Order ID
        razorpay_order_id = payment.gateway_order_id
        if not razorpay_order_id:
            try:
                rzp_order = create_razorpay_order(order)
                razorpay_order_id = rzp_order.get("id")

                with transaction.atomic():
                    payment.gateway_order_id = razorpay_order_id
                    payment.save(update_fields=["gateway_order_id"])

            except Exception as e:
                logger.error("Failed to initialize Razorpay order for #%s: %s", order.order_number, e)
                return Response(
                    {
                        "success": False,
                        "error": f"Unable to initiate online payment: {str(e)}",
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        amount_in_paise = int(Decimal(str(order.total_amount)) * 100)

        data = {
            "success": True,
            "order_number": order.order_number,
            "order_slug": order.slug,
            "payment_slug": payment.slug,
            "amount": str(order.total_amount),
            "amount_in_paise": amount_in_paise,
            "currency": getattr(settings, "RAZORPAY_CURRENCY", "INR"),
            "razorpay_key_id": getattr(settings, "RAZORPAY_KEY_ID", ""),
            "razorpay_order_id": razorpay_order_id,
            "user_name": order.shipping_name or request.user.get_full_name() or request.user.username,
            "user_email": getattr(request.user, "email", ""),
            "user_phone": order.shipping_phone or getattr(request.user, "phone", ""),
            "payment_status": payment.status,
        }

        return Response(data, status=status.HTTP_200_OK)


# ==============================================================================
# 2. PAYMENT VERIFY API VIEW (Replaces payment_verify)
# ==============================================================================
class PaymentVerifyAPIView(APIView):
    """
    POST /api/payments/verify/

    Verifies Razorpay payment signature after successful checkout modal return.
    Uses transaction.atomic with row locking (select_for_update) to guarantee:
    1. Race-condition protection against concurrent webhook callbacks.
    2. Atomic inventory deduction and order status confirmation.
    3. Idempotent success if payment was already confirmed by webhook.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        order_slug = request.data.get("order_slug", "").strip()
        razorpay_payment_id = request.data.get("razorpay_payment_id", "").strip()
        razorpay_order_id = request.data.get("razorpay_order_id", "").strip()
        razorpay_signature = request.data.get("razorpay_signature", "").strip()

        if not (order_slug and razorpay_payment_id and razorpay_order_id and razorpay_signature):
            return Response(
                {
                    "success": False,
                    "error": "Missing required verification parameters: order_slug, razorpay_order_id, razorpay_payment_id, and razorpay_signature."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        order = Order.objects.filter(slug=order_slug, user=request.user).first()
        if not order:
            return Response(
                {"success": False, "error": "Order not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # 1. Verify cryptographic HMAC SHA-256 signature
        is_valid = verify_razorpay_signature(
            razorpay_order_id=razorpay_order_id,
            razorpay_payment_id=razorpay_payment_id,
            razorpay_signature=razorpay_signature,
        )

        if is_valid:
            # 2. Complete payment atomically with row locking
            with transaction.atomic():
                locked_order = (
                    Order.objects.select_for_update()
                    .filter(pk=order.pk)
                    .first()
                )

                # Idempotency check: if already confirmed (e.g. by Webhook), reuse existing payment
                if locked_order.status == "confirmed":
                    payment = getattr(locked_order, "payment", None)
                    logger.info("Order #%s was already confirmed by another process.", locked_order.order_number)
                else:
                    payment = complete_order_payment(
                        order=locked_order,
                        transaction_id=razorpay_payment_id,
                        gateway_order_id=razorpay_order_id,
                        gateway_signature=razorpay_signature,
                        payment_method="online",
                    )
                    logger.info("Payment verified successfully for Order #%s (Payment ID: %s)", locked_order.order_number, razorpay_payment_id)

            return Response(
                {
                    "success": True,
                    "message": f"Payment of ₹{order.total_amount} verified successfully.",
                    "order_number": order.order_number,
                    "order_slug": order.slug,
                    "order_status": order.status,
                    "payment": PaymentSerializer(payment, context={"request": request}).data if payment else None,
                },
                status=status.HTTP_200_OK,
            )

        # Signature verification failed - record failure atomically
        with transaction.atomic():
            payment = Payment.objects.select_for_update().filter(order=order).first()
            if payment:
                payment.status = "failed"
                payment.save(update_fields=["status"])

        logger.warning("Payment signature verification failed for Order #%s", order.order_number)

        return Response(
            {
                "success": False,
                "error": "Payment signature verification failed. Please try again or contact support.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


# ==============================================================================
# 3. PAYMENT WEBHOOK API VIEW (Replaces payment_webhook)
# ==============================================================================
class PaymentWebhookAPIView(APIView):
    """
    POST /api/payments/webhook/

    Razorpay Asynchronous Webhook endpoint.
    Uses transaction.atomic and select_for_update to ensure thread-safe,
    atomic completion even if concurrent verify requests arrive.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        signature = request.headers.get("X-Razorpay-Signature", "")
        if not signature:
            logger.warning("Webhook received without X-Razorpay-Signature header.")
            return Response(
                {"error": "Missing X-Razorpay-Signature header."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        body = request.body
        is_valid = verify_razorpay_webhook_signature(body, signature)
        if not is_valid:
            logger.warning("Invalid webhook signature received.")
            return Response(
                {"error": "Invalid webhook signature."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            payload = json.loads(body.decode("utf-8"))
            event = payload.get("event")
            logger.info("Razorpay webhook event received: %s", event)

            if event in ["payment.captured", "order.paid"]:
                payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
                order_entity = payload.get("payload", {}).get("order", {}).get("entity", {})

                rzp_order_id = payment_entity.get("order_id") or order_entity.get("id")
                rzp_payment_id = payment_entity.get("id")

                if rzp_order_id:
                    with transaction.atomic():
                        payment = (
                            Payment.objects.select_for_update()
                            .filter(gateway_order_id=rzp_order_id)
                            .select_related("order")
                            .first()
                        )
                        if payment and payment.order:
                            locked_order = (
                                Order.objects.select_for_update()
                                .filter(pk=payment.order.pk)
                                .first()
                            )
                            # Only complete if not yet confirmed
                            if locked_order and locked_order.status != "confirmed":
                                complete_order_payment(
                                    order=locked_order,
                                    transaction_id=rzp_payment_id or payment.transaction_id or f"TXN-{rzp_order_id}",
                                    gateway_order_id=rzp_order_id,
                                    payment_method="online",
                                )
                                logger.info("Order #%s marked confirmed via Webhook event: %s", locked_order.order_number, event)

            return Response({"status": "ok", "message": "Webhook processed."}, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error("Error processing Razorpay webhook: %s", e, exc_info=True)
            return Response(
                {"error": f"Webhook processing error: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# ==============================================================================
# 4. PAYMENT LIST API VIEW
# ==============================================================================
class PaymentListAPIView(APIView):
    """
    GET /api/payments/ -> List user's payment history (supports ?status=)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        payments = (
            Payment.objects.filter(user=request.user)
            .select_related("order")
            .order_by("-created_at")
        )

        status_filter = request.query_params.get("status", "").strip()
        if status_filter:
            payments = payments.filter(status=status_filter)

        serializer = PaymentSerializer(payments, many=True, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)


# ==============================================================================
# 5. PAYMENT DETAIL API VIEW
# ==============================================================================
class PaymentDetailAPIView(APIView):
    """
    GET /api/payments/<identifier>/ -> Retrieve payment details by slug, transaction_id, or order_number
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, identifier):
        payment = (
            Payment.objects.filter(user=request.user)
            .filter(
                Q(slug=identifier)
                | Q(transaction_id=identifier)
                | Q(order__order_number=identifier)
                | Q(order__slug=identifier)
            )
            .select_related("order")
            .first()
        )

        if not payment:
            return Response(
                {"error": "Payment record not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = PaymentSerializer(payment, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)
