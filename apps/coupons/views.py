import json
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST
from apps.cart.utils import get_cart_count
from apps.cart.models import *
from .services import (
    validate_coupon_for_user,
    get_user_weekly_coupon_info,
    get_available_coupons,
    get_best_coupon_for_user,
)


def _get_cart_subtotal(user):
    if not user or not user.is_authenticated:
        return Decimal("0.00")
    cart_obj = Cart.objects.filter(user=user).first()
    if not cart_obj:
        return Decimal("0.00")
    return Decimal(str(sum(item.total_price for item in cart_obj.items.all())))


def public_coupon_list_view(request):
    """
    Public customer-facing page displaying active store coupons and deals.
    """
    subtotal = _get_cart_subtotal(request.user) if request.user.is_authenticated else Decimal("0.00")
    coupons = get_available_coupons(request.user if request.user.is_authenticated else None, subtotal)
    weekly_info = get_user_weekly_coupon_info(request.user) if request.user.is_authenticated else None
    best_coupon = get_best_coupon_for_user(request.user if request.user.is_authenticated else None, subtotal)
    cart_count = get_cart_count(request)

    context = {
        "coupons": coupons,
        "cart_subtotal": subtotal,
        "weekly_info": weekly_info,
        "best_coupon": best_coupon,
        "cart_count": cart_count,
    }
    return render(request, "coupons/public_coupon_list.html", context)


@login_required(login_url="login")
@require_POST
def apply_coupon_view(request):
    """
    Applies a coupon to the user's current checkout session.
    Validates cart subtotal, weekly limits, global limits, etc.
    Supports both JSON/AJAX and standard form submissions.
    Supports both 'coupon_code' and 'code' field names, and 'auto_apply=true'.
    """
    is_ajax = (
        request.headers.get("x-requested-with") == "XMLHttpRequest"
        or request.content_type == "application/json"
    )

    # Extract JSON body if applicable
    json_data = {}
    if request.content_type == "application/json" and request.body:
        try:
            json_data = json.loads(request.body)
        except Exception:
            json_data = {}

    coupon_code = (
        request.POST.get("coupon_code")
        or request.POST.get("code")
        or json_data.get("coupon_code")
        or json_data.get("code")
        or request.GET.get("coupon_code")
        or request.GET.get("code")
        or ""
    ).strip()

    is_auto_apply = (
        request.POST.get("auto_apply") in ["1", "true", "yes"]
        or json_data.get("auto_apply") in [True, 1, "1", "true", "yes"]
        or coupon_code.upper() == "AUTO"
    )

    redirect_target = request.POST.get("next") or json_data.get("next") or "checkout"

    subtotal = _get_cart_subtotal(request.user)
    if subtotal <= 0:
        msg = "Your cart is empty."
        if is_ajax:
            return JsonResponse({"success": False, "message": msg}, status=400)
        messages.error(request, msg)
        return redirect("cart")

    if is_auto_apply and not coupon_code:
        best = get_best_coupon_for_user(request.user, subtotal)
        if best:
            coupon_code = best.code
        else:
            msg = "No eligible coupon available to auto-apply for your cart amount."
            if is_ajax:
                return JsonResponse({"success": False, "message": msg}, status=400)
            messages.warning(request, msg)
            return redirect(redirect_target)

    if not coupon_code:
        msg = "Please enter a coupon code."
        if is_ajax:
            return JsonResponse({"success": False, "message": msg}, status=400)
        messages.error(request, msg)
        return redirect(redirect_target)

    is_valid, error_msg, coupon, discount = validate_coupon_for_user(
        coupon_code,
        request.user,
        subtotal
    )

    if not is_valid:
        if is_ajax:
            return JsonResponse({"success": False, "message": error_msg}, status=400)
        messages.error(request, error_msg)
        return redirect(redirect_target)

    # Store applied coupon code in session
    request.session["applied_coupon_code"] = coupon.code

    success_msg = f"✓ {coupon.code} applied successfully!"
    shipping_fee = Decimal("0.00") if subtotal >= 500 else Decimal("50.00")
    discounted_subtotal = max(Decimal("0.00"), subtotal - discount)
    new_total = discounted_subtotal + shipping_fee
    weekly_info = get_user_weekly_coupon_info(request.user)

    if is_ajax:
        return JsonResponse({
            "success": True,
            "message": success_msg,
            "coupon_code": coupon.code,
            "discount_amount": f"{discount:.2f}",
            "subtotal": f"{subtotal:.2f}",
            "shipping_fee": f"{shipping_fee:.2f}",
            "total": f"{new_total:.2f}",
            "weekly_usage": f"{weekly_info['usage_count']} / {weekly_info['weekly_limit']}",
            "remaining_uses": weekly_info["remaining"],
        })

    messages.success(request, success_msg)
    return redirect(redirect_target)


@login_required(login_url="login")
@require_POST
def remove_coupon_view(request):
    """
    Removes currently applied coupon from the user's session.
    """
    is_ajax = (
        request.headers.get("x-requested-with") == "XMLHttpRequest"
        or request.content_type == "application/json"
    )

    redirect_target = request.POST.get("next") or "checkout"

    removed_code = request.session.pop("applied_coupon_code", None)
    subtotal = _get_cart_subtotal(request.user)
    shipping_fee = Decimal("0.00") if subtotal >= 500 else Decimal("50.00")
    new_total = subtotal + shipping_fee
    weekly_info = get_user_weekly_coupon_info(request.user)

    msg = f"Coupon {removed_code} removed." if removed_code else "No coupon applied."

    if is_ajax:
        return JsonResponse({
            "success": True,
            "message": msg,
            "subtotal": f"{subtotal:.2f}",
            "shipping_fee": f"{shipping_fee:.2f}",
            "total": f"{new_total:.2f}",
            "weekly_usage": f"{weekly_info['usage_count']} / {weekly_info['weekly_limit']}",
            "remaining_uses": weekly_info["remaining"],
        })

    messages.info(request, msg)
    return redirect(redirect_target)