import json
import logging
from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.urls import reverse
from django.conf import settings
from django.contrib import messages

from apps.order.models import Order
from .models import Payment
from .services import (
    create_razorpay_order,
    verify_razorpay_signature,
    verify_razorpay_webhook_signature,
    complete_order_payment,
)

logger = logging.getLogger(__name__)


@login_required(login_url="login")
def payment_process(request, order_slug):
    """
    Renders the payment processing page where user can complete online payment
    via the Razorpay Checkout popup (UPI, Cards, NetBanking).
    """
    order = get_object_or_404(
        Order.objects.prefetch_related(
            "items__variant__product",
            "items__variant__color"
        ),
        slug=order_slug,
        user=request.user
    )

    # If order is already confirmed, redirect directly to confirmation
    if order.status == "confirmed":
        messages.info(request, "This order has already been paid and confirmed.")
        return redirect("order_confirmation", order_slug=order.slug)

    payment, created = Payment.objects.get_or_create(
        order=order,
        defaults={
            "user": request.user,
            "amount": order.total_amount,
            "payment_method": "online",
            "status": "pending",
        }
    )

    # Generate or reuse Razorpay Order ID
    razorpay_order_id = payment.gateway_order_id
    if not razorpay_order_id:
        try:
            rzp_order = create_razorpay_order(order)
            razorpay_order_id = rzp_order.get("id")
            payment.gateway_order_id = razorpay_order_id
            payment.save(update_fields=["gateway_order_id"])
        except Exception as e:
            logger.error("Failed to initialize Razorpay order for #%s: %s", order.order_number, e)
            messages.error(request, f"Unable to initiate online payment: {e}")
            return render(request, "payment/process.html", {
                "order": order,
                "payment": payment,
                "error": str(e),
                "razorpay_key_id": settings.RAZORPAY_KEY_ID,
            })

    amount_in_paise = int(Decimal(str(order.total_amount)) * 100)

    context = {
        "order": order,
        "payment": payment,
        "razorpay_order_id": razorpay_order_id,
        "razorpay_key_id": settings.RAZORPAY_KEY_ID,
        "amount_in_paise": amount_in_paise,
        "currency": getattr(settings, "RAZORPAY_CURRENCY", "INR"),
        "user_name": order.shipping_name or request.user.get_full_name() or request.user.username,
        "user_email": getattr(request.user, "email", ""),
        "user_phone": order.shipping_phone or getattr(request.user, "phone", ""),
    }

    return render(request, "payment/process.html", context)


@login_required(login_url="login")
def payment_verify(request):
    """
    Handles payment verification after Razorpay checkout returns.
    Accepts JSON (via fetch) or standard form POST.
    """
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid request method.")

    # Support both JSON payload and standard form data
    if request.content_type == "application/json":
        try:
            data = json.loads(request.body.decode("utf-8"))
        except Exception:
            return JsonResponse({"status": "error", "message": "Invalid JSON format."}, status=400)
    else:
        data = request.POST.dict()

    order_slug = data.get("order_slug", "").strip()
    razorpay_payment_id = data.get("razorpay_payment_id", "").strip()
    razorpay_order_id = data.get("razorpay_order_id", "").strip()
    razorpay_signature = data.get("razorpay_signature", "").strip()

    if not (order_slug and razorpay_payment_id and razorpay_order_id and razorpay_signature):
        return JsonResponse({
            "status": "error",
            "message": "Missing required verification parameters."
        }, status=400)

    order = get_object_or_404(Order, slug=order_slug, user=request.user)

    is_valid = verify_razorpay_signature(
        razorpay_order_id=razorpay_order_id,
        razorpay_payment_id=razorpay_payment_id,
        razorpay_signature=razorpay_signature,
    )

    if is_valid:
        complete_order_payment(
            order=order,
            transaction_id=razorpay_payment_id,
            gateway_order_id=razorpay_order_id,
            gateway_signature=razorpay_signature,
            payment_method="online",
        )

        redirect_url = reverse("order_confirmation", kwargs={"order_slug": order.slug})
        messages.success(request, f"Payment of ₹{order.total_amount} verified successfully!")

        if request.content_type == "application/json":
            return JsonResponse({
                "status": "success",
                "message": "Payment verified successfully.",
                "redirect_url": redirect_url
            })
        return redirect(redirect_url)

    # Signature verification failed
    payment = getattr(order, "payment", None)
    if payment:
        payment.status = "failed"
        payment.save(update_fields=["status"])

    logger.warning("Payment signature verification failed for Order #%s", order.order_number)
    messages.error(request, "Payment verification failed. Please try again.")

    if request.content_type == "application/json":
        return JsonResponse({
            "status": "error",
            "message": "Signature verification failed."
        }, status=400)

    return redirect("payment_process", order_slug=order.slug)


@csrf_exempt
def payment_webhook(request):
    """
    Razorpay Webhook endpoint for asynchronous payment confirmation.
    Ensures order status is updated even if the user drops connection or closes tab.
    """
    if request.method != "POST":
        return HttpResponse(status=405)

    signature = request.headers.get("X-Razorpay-Signature", "")
    if not signature:
        logger.warning("Webhook received without X-Razorpay-Signature header.")
        return HttpResponseBadRequest("Missing signature header.")

    body = request.body
    is_valid = verify_razorpay_webhook_signature(body, signature)
    if not is_valid:
        logger.warning("Invalid webhook signature received.")
        return HttpResponseBadRequest("Invalid signature.")

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
                payment = Payment.objects.filter(gateway_order_id=rzp_order_id).select_related("order").first()
                if payment and payment.order and payment.order.status != "confirmed":
                    complete_order_payment(
                        order=payment.order,
                        transaction_id=rzp_payment_id or payment.transaction_id or f"TXN-{rzp_order_id}",
                        gateway_order_id=rzp_order_id,
                        payment_method="online",
                    )
                    logger.info("Order #%s marked confirmed via Webhook event: %s", payment.order.order_number, event)

        return HttpResponse(status=200)
    except Exception as e:
        logger.error("Error processing Razorpay webhook: %s", e, exc_info=True)
        return HttpResponse(status=500)
