from datetime import timedelta
from decimal import Decimal
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import Coupon, CouponConfiguration, CouponUsage


def get_current_week_bounds(dt=None):
    """
    Returns (start_of_week, end_of_week) for the week containing dt (defaulting to current time).
    The week strictly starts on Monday 00:00:00 and ends on Sunday 23:59:59.999999.
    Timezone-aware using project's active timezone.
    """
    now = dt or timezone.now()
    current_tz = timezone.get_current_timezone()
    now_local = now.astimezone(current_tz)

    start_of_week = (now_local - timedelta(days=now_local.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    end_of_week = (start_of_week + timedelta(days=6)).replace(
        hour=23, minute=59, second=59, microsecond=999999
    )
    return start_of_week, end_of_week


def get_user_weekly_coupon_usage(user, dt=None):
    """
    Counts the number of successful coupon usages for the given authenticated user
    during the current week (Monday 00:00 to Sunday 23:59:59).
    """
    if not user or not user.is_authenticated:
        return 0

    start_of_week, end_of_week = get_current_week_bounds(dt)
    return CouponUsage.objects.filter(
        user=user,
        used_at__gte=start_of_week,
        used_at__lte=end_of_week
    ).count()


def can_user_use_coupon(user, coupon=None, dt=None):
    """
    Determines if the user has remaining weekly coupon uses.
    If coupon is provided, uses coupon.weekly_user_limit (if defined),
    otherwise falls back to CouponConfiguration.get_weekly_limit().
    Returns (can_use: bool, error_message: str).
    """
    if not user or not user.is_authenticated:
        return False, "Please log in to use coupons."

    usage_count = get_user_weekly_coupon_usage(user, dt)
    weekly_limit = (
        coupon.weekly_user_limit
        if (coupon and getattr(coupon, "weekly_user_limit", None) is not None)
        else CouponConfiguration.get_weekly_limit()
    )

    if usage_count >= weekly_limit:
        return False, f"Weekly coupon limit reached. You can use coupons up to {weekly_limit} times per week."

    return True, ""


def get_user_weekly_coupon_info(user, coupon=None, dt=None):
    """
    Returns user weekly coupon stats for UI presentation.
    """
    weekly_limit = (
        coupon.weekly_user_limit
        if (coupon and getattr(coupon, "weekly_user_limit", None) is not None)
        else CouponConfiguration.get_weekly_limit()
    )
    if not user or not user.is_authenticated:
        return {
            "usage_count": 0,
            "weekly_limit": weekly_limit,
            "remaining": weekly_limit,
            "is_limit_reached": False,
        }

    usage_count = get_user_weekly_coupon_usage(user, dt)
    remaining = max(0, weekly_limit - usage_count)
    return {
        "usage_count": usage_count,
        "weekly_limit": weekly_limit,
        "remaining": remaining,
        "is_limit_reached": usage_count >= weekly_limit,
    }


def validate_coupon_for_user(
    coupon_code,
    user,
    order_amount,
    dt=None,
    coupon=None,
):
    """
    Validates a coupon for an order following the strict validation order:
    1. User is authenticated.
    2. Coupon exists (case-insensitive).
    3. Coupon is active.
    4. Coupon is within valid_from and valid_until.
    5. User has not exceeded weekly coupon limit.
    6. Coupon's global usage limit has not been reached.
    7. User has not exceeded coupon's per_user_limit.
    8. Cart meets minimum_order_amount.
    9. Calculate discount.
    10. Ensure discount does not exceed order total.

    Returns:
        (is_valid: bool, error_message: str, coupon: Coupon or None, discount_amount: Decimal)
    """
    # 1. User is authenticated
    if not user or not user.is_authenticated:
        return False, "Please log in to use coupons.", None, Decimal("0.00")

    if not coupon_code:
        return False, "Invalid coupon code.", None, Decimal("0.00")

    # 2. Coupon exists (case-insensitive)
    code_clean = str(coupon_code).strip()
    coupon = Coupon.objects.filter(code__iexact=code_clean).first()
    if not coupon:
        return False, "Invalid coupon code.", None, Decimal("0.00")

    # 3. Coupon is active
    if not coupon.is_active:
        return False, "This coupon is not active.", coupon, Decimal("0.00")

    # 4. Coupon is currently within valid_from and valid_until
    now = dt or timezone.now()
    if now < coupon.valid_from:
        return False, f"This coupon is not active yet. It starts on {coupon.valid_from.strftime('%d %b %Y')}.", coupon, Decimal("0.00")
    if now > coupon.valid_until:
        return False, "This coupon has expired.", coupon, Decimal("0.00")

    # 5. User has not exceeded the weekly coupon limit
    can_use_weekly, weekly_error = can_user_use_coupon(user, coupon=coupon, dt=now)
    if not can_use_weekly:
        limit = coupon.weekly_user_limit if (coupon and getattr(coupon, "weekly_user_limit", None) is not None) else CouponConfiguration.get_weekly_limit()
        return False, f"Weekly coupon limit reached. You can use coupons up to {limit} times per week. (You have reached your weekly coupon limit of {limit} uses.)", coupon, Decimal("0.00")

    # 6. Coupon's global usage limit has not been reached
    if coupon.usage_limit is not None and coupon.used_count >= coupon.usage_limit:
        return False, "This coupon has reached its usage limit.", coupon, Decimal("0.00")

    # 7. User has not exceeded the coupon's individual per_user_limit
    if coupon.per_user_limit is not None:
        user_usage_count = CouponUsage.objects.filter(coupon=coupon, user=user).count()
        if user_usage_count >= coupon.per_user_limit:
            return False, "You have already used this coupon the maximum allowed number of times.", coupon, Decimal("0.00")

    # 8. Cart meets minimum_order_amount
    order_amount_dec = Decimal(str(order_amount or 0))
    if order_amount_dec < coupon.minimum_order_amount:
        min_fmt = int(coupon.minimum_order_amount) if coupon.minimum_order_amount % 1 == 0 else coupon.minimum_order_amount
        return False, f"Minimum order amount is ₹{min_fmt:,}.", coupon, Decimal("0.00")

    # 9. Calculate discount & 10. Ensure discount does not exceed order total
    discount_amount = coupon.calculate_discount(order_amount_dec)

    return True, "", coupon, discount_amount


@transaction.atomic
def record_coupon_usage(order, coupon=None, discount_amount=None, used_at=None):
    """
    Safely and idempotently records coupon usage for an order upon successful order placement/payment.
    - Runs inside a database transaction.
    - Prevents duplicate usage records for the same order.
    - Increments coupon used_count.
    - Supports both Cash on Delivery (pending) and online payments (completed).
    - Returns CouponUsage instance or None if not eligible.
    """
    # Verify order is not cancelled and payment is not failed
    payment = getattr(order, "payment", None)
    if payment and payment.status == "failed":
        return None
    if getattr(order, "status", "") == "cancelled":
        return None

    target_coupon = coupon or getattr(order, "coupon", None)
    if not target_coupon:
        return None

    # Check if already recorded for this order (idempotency guard)
    existing_usage = CouponUsage.objects.filter(order=order).first()
    if existing_usage:
        return existing_usage

    # Lock coupon row for update to prevent concurrent race conditions
    locked_coupon = Coupon.objects.select_for_update().get(pk=target_coupon.pk)

    actual_discount = (
        discount_amount
        if discount_amount is not None
        else getattr(order, "discount_amount", Decimal("0.00"))
    )

    usage = CouponUsage.objects.create(
        coupon=locked_coupon,
        user=order.user,
        order=order,
        discount_amount=actual_discount,
        used_at=used_at or timezone.now()
    )

    # Increment used_count safely
    Coupon.objects.filter(pk=locked_coupon.pk).update(used_count=F("used_count") + 1)
    locked_coupon.refresh_from_db(fields=["used_count"])

    return usage


def get_available_coupons(user=None, cart_amount=Decimal("0.00"), dt=None):
    """
    Returns active, currently valid coupons that customers can view and apply.
    Annotates each coupon with:
    - qualifies: bool (cart_amount >= minimum_order_amount)
    - amount_needed: Decimal (max(0, minimum_order_amount - cart_amount))
    - estimated_discount: Decimal (discount calculated on cart_amount)
    """

    now = dt or timezone.now()
    qs = Coupon.objects.filter(
        is_active=True,
        valid_from__lte=now,
        valid_until__gte=now,
    ).order_by("minimum_order_amount", "-discount_value")

    cart_amount_dec = Decimal(str(cart_amount or 0))
    valid_coupons = []
    for c in qs:
        # Check global limit
        if c.usage_limit is not None and c.used_count >= c.usage_limit:
            continue
        # Check per-user lifetime limit if user is authenticated
        if user and user.is_authenticated and c.per_user_limit is not None:
            user_count = CouponUsage.objects.filter(coupon=c, user=user).count()
            if user_count >= c.per_user_limit:
                continue

        qualifies = cart_amount_dec >= c.minimum_order_amount
        needed = max(Decimal("0.00"), c.minimum_order_amount - cart_amount_dec)
        discount = c.calculate_discount(cart_amount_dec) if qualifies else Decimal("0.00")

        c.qualifies = qualifies
        c.amount_needed = needed
        c.estimated_discount = discount
        valid_coupons.append(c)

    return valid_coupons


def get_best_coupon_for_user(user=None, cart_amount=Decimal("0.00"), dt=None):
    """
    Finds and returns the single best valid coupon that yields the highest
    discount for this user and cart amount. Returns None if no qualifying coupon exists.
    """
    coupons = get_available_coupons(user=user, cart_amount=cart_amount, dt=dt)
    qualifying = [
        c for c in coupons
        if getattr(c, "qualifies", False) and getattr(c, "estimated_discount", Decimal("0.00")) > Decimal("0.00")
    ]
    if not qualifying:
        return None

    # Pick the coupon with the highest discount, breaking ties by lowest minimum_order_amount
    return max(
        qualifying,
        key=lambda c: (c.estimated_discount, -c.minimum_order_amount)
    )
