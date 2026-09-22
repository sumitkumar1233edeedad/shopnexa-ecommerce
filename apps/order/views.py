import uuid
from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db import transaction
from django.db.models import Q

from .models import Order, OrderItem
from apps.cart.models import Cart
from apps.accounts.models import Address
from apps.payment.models import Payment
from apps.coupons.services import (
    validate_coupon_for_user,
    get_user_weekly_coupon_info,
    record_coupon_usage,
    get_available_coupons,
    get_best_coupon_for_user,
)
from apps.cart.utils import *

 

@login_required(login_url="login")
def checkout_view(request):

    cart_obj, _ = Cart.objects.get_or_create(
        user=request.user
    )

    items = cart_obj.items.select_related(
        "product__product",
        "product__color"
    ).all()

    if not items.exists():
        messages.warning(
            request,
            "Your cart is empty. Please add products before checking out."
        )
        return redirect("cart")

    subtotal = Decimal(str(sum(
        item.total_price
        for item in items
    )))

    # Compute available coupons and best coupon for auto-apply
    available_coupons = get_available_coupons(request.user, subtotal)
    best_coupon = get_best_coupon_for_user(request.user, subtotal)

    # Check for direct URL parameter apply_coupon=CODE or auto_apply=1
    url_coupon = request.GET.get("apply_coupon", "").strip()
    auto_apply_param = request.GET.get("auto_apply", "").strip()

    if url_coupon:
        is_valid, error_msg, coupon, discount = validate_coupon_for_user(
            url_coupon,
            request.user,
            subtotal
        )
        if is_valid:
            request.session["applied_coupon_code"] = coupon.code
            messages.success(request, f"✓ Coupon {coupon.code} applied successfully!")
        else:
            messages.error(request, f"Coupon '{url_coupon}' could not be applied: {error_msg}")
    elif auto_apply_param in ["1", "true", "yes"] and not request.session.get("applied_coupon_code"):
        if best_coupon:
            request.session["applied_coupon_code"] = best_coupon.code
            messages.success(request, f"✓ Best coupon {best_coupon.code} auto-applied! You saved ₹{best_coupon.estimated_discount:.2f}")

    # Coupon Handling
    applied_code = request.session.get("applied_coupon_code")
    applied_coupon = None
    discount_amount = Decimal("0.00")

    if applied_code:
        is_valid, error_msg, coupon, discount = validate_coupon_for_user(
            applied_code,
            request.user,
            subtotal
        )
        if is_valid:
            applied_coupon = coupon
            discount_amount = discount
        else:
            request.session.pop("applied_coupon_code", None)
            messages.warning(
                request,
                f"Applied coupon '{applied_code}' is no longer valid: {error_msg}"
            )

    discounted_subtotal = max(Decimal("0.00"), subtotal - discount_amount)
    shipping_fee = Decimal("0.00") if subtotal >= 500 else Decimal("50.00")
    grand_total = discounted_subtotal + shipping_fee

    weekly_coupon_info = get_user_weekly_coupon_info(request.user)

    saved_addresses = (
        Address.objects
        .filter(user=request.user)
        .order_by("-is_default", "-id")
    )

    context = {
        "items": items,
        "subtotal": subtotal,
        "shipping_fee": shipping_fee,
        "total": grand_total,
        "saved_addresses": saved_addresses,
        "user": request.user,
        "applied_coupon": applied_coupon,
        "discount_amount": discount_amount,
        "weekly_coupon_info": weekly_coupon_info,
        "available_coupons": available_coupons,
        "best_coupon": best_coupon,
    }

    return render(
        request,
        "accounts/checkout.html",
        context
    )

 

@login_required(login_url="login")
def place_order_view(request):

    if request.method != "POST":
        return redirect("checkout")

   
    cart_obj = (
        Cart.objects
        .filter(user=request.user)
        .first()
    )

    if not cart_obj or not cart_obj.items.exists():
        messages.error(
            request,
            "Your cart is empty."
        )
        return redirect("cart")

    items = cart_obj.items.select_related(
        "product__product",
        "product__color"
    ).all()

    
    subtotal = Decimal(str(sum(
        item.total_price
        for item in items
    )))

    applied_coupon_code = request.session.get("applied_coupon_code")
    applied_coupon = None
    discount_amount = Decimal("0.00")

    if applied_coupon_code:
        is_valid, error_msg, coupon, discount = validate_coupon_for_user(
            applied_coupon_code,
            request.user,
            subtotal
        )
        if is_valid:
            applied_coupon = coupon
            discount_amount = discount
        else:
            request.session.pop("applied_coupon_code", None)
            messages.warning(
                request,
                f"Coupon '{applied_coupon_code}' could not be applied: {error_msg}"
            )

    discounted_subtotal = max(Decimal("0.00"), subtotal - discount_amount)
    shipping_fee = Decimal("0.00") if subtotal >= 500 else Decimal("50.00")
    grand_total = discounted_subtotal + shipping_fee
 
    address_slug = (
        request.POST.get("address_slug", "").strip()
        or request.POST.get("address_id", "").strip()
    )

    if address_slug and address_slug != "new":

        addr_q = Q(slug=address_slug)
        if address_slug.isdigit():
            addr_q |= Q(id=int(address_slug))

        saved_addr = (
            Address.objects
            .filter(
                addr_q,
                user=request.user
            )
            .first()
        )

        if not saved_addr:
            messages.error(
                request,
                "Selected address was not found."
            )
            return redirect("checkout")

        shipping_name = saved_addr.name
        shipping_phone = saved_addr.phone or ""
        shipping_city = saved_addr.city
        shipping_pincode = saved_addr.pincode

        full_address = (
            f"{saved_addr.address_line}, "
            f"{saved_addr.locality or ''}, "
            f"{saved_addr.city}, "
            f"{saved_addr.state} - "
            f"{saved_addr.pincode}"
        )

        # Clean duplicate commas/spaces
        full_address = (
            full_address
            .replace(", ,", ",")
            .replace(" ,", ",")
        )

    else:

    
        shipping_name = request.POST.get("name", "").strip()
        shipping_phone = request.POST.get("phone", "").strip()
        address_line = request.POST.get("address_line", "").strip()
        locality = request.POST.get("locality", "").strip()
        shipping_city = request.POST.get("city", "").strip()
        state = request.POST.get("state", "").strip()
        shipping_pincode = request.POST.get("pincode", "").strip()

        # Required fields
        if (
            not shipping_name
            or not address_line
            or not shipping_city
            or not shipping_pincode
        ):
            messages.error(
                request,
                "Please fill in all required shipping fields."
            )
            return redirect("checkout")

        full_address = (
            f"{address_line}, "
            f"{locality}, "
            f"{shipping_city}, "
            f"{state} - "
            f"{shipping_pincode}"
        )

        full_address = (
            full_address
            .replace(", ,", ",")
            .replace(" ,", ",")
        )

         

        if request.POST.get("save_address"):

            Address.objects.create(
                user=request.user,
                name=shipping_name,
                phone=shipping_phone,
                address_line=address_line,
                locality=locality,
                city=shipping_city,
                state=state,
                pincode=shipping_pincode,
                address_type="HOME",
                is_default=not Address.objects.filter(
                    user=request.user
                ).exists()
            )

 

    payment_method = request.POST.get(
        "payment_method",
        "cod"
    ).lower()

    valid_methods = [
        "cod",
        "online",
        "razorpay",
        "upi",
        "card",
        "netbanking",
    ]

    if payment_method not in valid_methods:
        payment_method = "cod"

    # Pre-check stock availability for all cart items before placing order
    for item in items:
        if hasattr(item.product, "stock"):
            stock = item.product.stock
            if stock.quantity < item.quantity:
                messages.error(
                    request,
                    f"Insufficient stock for {item.product.product.name} (SKU: {item.product.sku}). Available: {stock.quantity}"
                )
                return redirect("cart")

    timestamp = timezone.now().strftime(
        "%Y%m%d%H%M"
    )

    short_uuid = (
        uuid.uuid4()
        .hex[:6]
        .upper()
    )

    order_number = (
        f"ORD-{timestamp}-{short_uuid}"
    )

    is_online = payment_method != "cod"
    order_status = "pending_payment" if is_online else "pending"

    order = Order.objects.create(
        user=request.user,
        order_number=order_number,
        status=order_status,
        total_amount=grand_total,
        coupon=applied_coupon,
        discount_amount=discount_amount,
        shipping_name=shipping_name,
        shipping_phone=shipping_phone,
        shipping_city=shipping_city,
        shipping_pincode=shipping_pincode,
        shipping_address=full_address,
    )

    for item in items:
        OrderItem.objects.create(
            order=order,
            variant=item.product,
            quantity=item.quantity,
            price=item.product.price,
        )

    # ---------------------------------------------------------
    # CASE 1: CASH ON DELIVERY (COD)
    # ---------------------------------------------------------
    if not is_online:
        # Deduct stock immediately for COD
        for item in items:
            if hasattr(item.product, "stock"):
                stock = item.product.stock
                if stock.quantity >= item.quantity:
                    stock.quantity -= item.quantity
                    stock.save(update_fields=["quantity"])

        Payment.objects.create(
            user=request.user,
            order=order,
            payment_method="cod",
            amount=grand_total,
            status="pending",
        )

        if applied_coupon:
            record_coupon_usage(order, coupon=applied_coupon, discount_amount=discount_amount)

        request.session.pop("applied_coupon_code", None)
        cart_obj.items.all().delete()

        messages.success(
            request,
            f"Order #{order.order_number} has been placed successfully!"
        )

        return redirect(
            "order_confirmation",
            order_slug=order.slug
        )

    # ---------------------------------------------------------
    # CASE 2: ONLINE PAYMENT (Razorpay)
    # ---------------------------------------------------------
    gateway_order_id = None
    try:
        from apps.payment.services import create_razorpay_order
        rzp_order = create_razorpay_order(order)
        gateway_order_id = rzp_order.get("id")
    except Exception as e:
        # If Razorpay order creation fails, user can still retry on payment_process page
        pass

    Payment.objects.create(
        user=request.user,
        order=order,
        payment_method="online",
        gateway_order_id=gateway_order_id,
        amount=grand_total,
        status="pending",
    )

    # Keep cart and stock intact until payment signature is verified
    return redirect(
        "payment_process",
        order_slug=order.slug
    )
 
@login_required(login_url="login")
def order_confirmation_view(
    request,
    order_slug
):

    order = get_object_or_404(
        Order.objects.prefetch_related(
            "items__variant__product",
            "items__variant__color"
        ),
        slug=order_slug,
        user=request.user
    )

    payment = getattr(
        order,
        "payment",
        None
    )

    return render(
        request,
        "order/confirmation.html",
        {
            "order": order,
            "payment": payment,
        }
    )
 

@login_required(login_url="login")
def my_orders_view(request):

    orders = (
        Order.objects
        .filter(user=request.user)
        .prefetch_related(
            "items__variant__product",
            "items__variant__color"
        )
        .order_by("-created_at")
    )
    cart_count = get_cart_count(request)
    return render(
        request,
        "order/my_orders.html",
        {
            "orders": orders,
            "cart_count": cart_count,
        }
    )

 

@login_required(login_url="login")
def order_detail_view(
    request,
    order_slug
):

    order = get_object_or_404(
        Order.objects.prefetch_related(
            "items__variant__product",
            "items__variant__color"
        ),
        slug=order_slug,
        user=request.user
    )

    payment = getattr(
        order,
        "payment",
        None
    )
    cart_count = get_cart_count(request)

    return render(
        request,
        "order/order_detail.html",
        {
            "order": order,
            "payment": payment,
            "cart_count": cart_count,
        }
    )
 