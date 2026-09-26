from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from api_apps.accounts_api.views import merge_session_cart_to_user
from .models import Cart, CartItem
from apps.products.models import Product, ProductVariant
from apps.coupons.services import (
    validate_coupon_for_user,
    get_available_coupons,
    get_best_coupon_for_user,
    get_user_weekly_coupon_info,
)


# ============================================================
# GET VARIANT BY SLUG
# ============================================================

def _get_variant(variant_slug):
    """
    Get an active ProductVariant using its slug.

    Also supports Product slug as a fallback:
    /cart/add/<product-slug>/
    """

    # First try ProductVariant slug
    variant = ProductVariant.objects.select_related(
        "product",
        "color"
    ).filter(
        slug=variant_slug,
        is_active=True
    ).first()

    if variant:
        return variant

    # Fallback: if the supplied slug belongs to a Product,
    # use its default variant.
    product = Product.objects.filter(
        slug=variant_slug,
        is_active=True
    ).first()

    if product:
        return product.default_variant

    return None


# ============================================================
# MERGE SESSION CART INTO USER CART
# ============================================================

# def merge_session_cart_to_user(request, user):
#     """
#     Move guest/session cart into the logged-in user's database cart.

#     Session cart format:

#     {
#         "black-tshirt-large": {
#             "quantity": 2
#         }
#     }

#     If the same variant already exists in the database cart,
#     quantities are added together.
#     """

#     session_cart = request.session.get("cart", {})

#     if not session_cart:
#         return

#     cart_obj, _ = Cart.objects.get_or_create(user=user)

#     with transaction.atomic():

#         for variant_slug, data in list(session_cart.items()):

#             # Find variant by slug
#             variant = ProductVariant.objects.filter(
#                 slug=variant_slug,
#                 is_active=True
#             ).first()

#             # Variant no longer exists / inactive
#             if not variant:
#                 continue

#             # Support both:
#             # {"quantity": 2}
#             # 2
#             if isinstance(data, dict):
#                 quantity = data.get("quantity", 1)
#             else:
#                 quantity = data

#             try:
#                 quantity = int(quantity)
#             except (ValueError, TypeError):
#                 quantity = 1

#             if quantity < 1:
#                 continue

#             # Check if variant already exists in user's cart
#             item, created = CartItem.objects.get_or_create(
#                 cart=cart_obj,
#                 product=variant,
#                 defaults={
#                     "quantity": quantity
#                 }
#             )

#             if not created:
#                 item.quantity += quantity
#                 item.save(update_fields=["quantity"])

#     # Clear guest cart after successful merge
#     request.session["cart"] = {}
#     request.session.modified = True


# ============================================================
# CART
# ============================================================
def cart(request):
    items = []
    subtotal = Decimal("0.00")

    # ============================================================
    # LOGGED-IN USER
    # ============================================================

    if request.user.is_authenticated:
        cart_obj, _ = Cart.objects.get_or_create(
            user=request.user
        )

        db_items = (
            cart_obj.items
            .select_related(
                "product__product",
                "product__color",
            )
            .all()
        )

        for item in db_items:
            items.append({
                "variant": item.product,
                "product": item.product.product,
                "quantity": item.quantity,
                "price": item.product.price,
                "total_price": item.total_price,
            })

            subtotal += item.total_price

    # ============================================================
    # GUEST USER
    # ============================================================

    else:
        session_cart = request.session.get("cart", {})

        for variant_slug, data in list(session_cart.items()):

            variant = (
                ProductVariant.objects
                .select_related(
                    "product",
                    "color",
                )
                .filter(
                    slug=variant_slug,
                    is_active=True,
                )
                .first()
            )

            # Remove invalid variant
            if not variant:
                del session_cart[variant_slug]
                request.session.modified = True
                continue

            # Get quantity
            if isinstance(data, dict):
                qty = data.get("quantity", 1)
            else:
                qty = data

            try:
                qty = int(qty)
            except (ValueError, TypeError):
                qty = 1

            if qty < 1:
                del session_cart[variant_slug]
                request.session.modified = True
                continue

            line_total = variant.price * qty

            items.append({
                "variant": variant,
                "product": variant.product,
                "quantity": qty,
                "price": variant.price,
                "total_price": line_total,
            })

            subtotal += line_total

    # ============================================================
    # TOTALS
    # ============================================================

    subtotal_dec = Decimal(str(subtotal))

    applied_code = request.session.get(
        "applied_coupon_code"
    )

    applied_coupon = None
    discount_amount = Decimal("0.00")
    available_coupons = []
    best_coupon = None
    weekly_coupon_info = None

    # ============================================================
    # COUPONS
    # ============================================================

    coupon_user = (
        request.user
        if request.user.is_authenticated
        else None
    )

    # ONLY ONE get_available_coupons() CALL
    available_coupons = get_available_coupons(
        user=coupon_user,
        cart_amount=subtotal_dec,
    )

    # ============================================================
    # FIND BEST COUPON FROM ALREADY LOADED COUPONS
    # ============================================================

    qualifying_coupons = [
        coupon
        for coupon in available_coupons
        if (
            getattr(coupon, "qualifies", False)
            and getattr(
                coupon,
                "estimated_discount",
                Decimal("0.00"),
            ) > Decimal("0.00")
        )
    ]

    if qualifying_coupons:
        best_coupon = max(
            qualifying_coupons,
            key=lambda coupon: (
                coupon.estimated_discount,
                -coupon.minimum_order_amount,
            ),
        )

    # ============================================================
    # VALIDATE APPLIED COUPON
    # ============================================================

    if (
        request.user.is_authenticated
        and applied_code
    ):
        # Reuse coupon already fetched above.
        applied_available_coupon = next(
            (
                coupon
                for coupon in available_coupons
                if coupon.code.lower()
                == applied_code.strip().lower()
            ),
            None,
        )

        is_valid, error_message, coupon, discount = (
            validate_coupon_for_user(
                applied_code,
                request.user,
                subtotal_dec,
                coupon=applied_available_coupon,
            )
        )

        if is_valid:
            applied_coupon = coupon
            discount_amount = discount

        else:
            request.session.pop(
                "applied_coupon_code",
                None,
            )

    # ============================================================
    # WEEKLY COUPON INFO
    # ============================================================

    if request.user.is_authenticated:
        weekly_coupon_info = (
            get_user_weekly_coupon_info(
                request.user
            )
        )

    # ============================================================
    # SHIPPING
    # ============================================================

    discounted_subtotal = max(
        Decimal("0.00"),
        subtotal_dec - discount_amount,
    )

    shipping_fee = (
        Decimal("0.00")
        if (
            subtotal_dec >= Decimal("500.00")
            or subtotal_dec == Decimal("0.00")
        )
        else Decimal("50.00")
    )

    grand_total = (
        discounted_subtotal
        + shipping_fee
    )

    # ============================================================
    # CART COUNT
    # ============================================================

    cart_count = sum(
        item["quantity"]
        for item in items
    )

    # ============================================================
    # CONTEXT
    # ============================================================

    context = {
        "items": items,
        "subtotal": subtotal_dec,
        "shipping_fee": shipping_fee,
        "discount_amount": discount_amount,
        "applied_coupon": applied_coupon,
        "total": grand_total,
        "cart_total": grand_total,
        "cart_count": cart_count,
        "available_coupons": available_coupons,
        "best_coupon": best_coupon,
        "weekly_coupon_info": weekly_coupon_info,
    }

    return render(
        request,
        "cart/cart.html",
        context,
    )


# ============================================================
# ADD TO CART
# ============================================================

def add_to_cart(request, variant_slug):

    variant = _get_variant(variant_slug)

    if not variant:
        messages.error(
            request,
            "Product not found or currently unavailable."
        )
        return redirect("cart")

    # --------------------------------------------------------
    # QUANTITY
    # --------------------------------------------------------

    try:
        quantity = int(
            request.POST.get("quantity", 1)
        )

        if quantity < 1:
            quantity = 1

    except (ValueError, TypeError):
        quantity = 1

    # --------------------------------------------------------
    # LOGGED-IN USER
    # --------------------------------------------------------

    if request.user.is_authenticated:

        cart_obj, _ = Cart.objects.get_or_create(
            user=request.user
        )

        item, created = CartItem.objects.get_or_create(
            cart=cart_obj,
            product=variant,
            defaults={
                "quantity": quantity
            }
        )

        if not created:
            item.quantity += quantity
            item.save(update_fields=["quantity"])

    # --------------------------------------------------------
    # GUEST USER
    # --------------------------------------------------------

    else:

        session_cart = request.session.get(
            "cart",
            {}
        )

        # IMPORTANT:
        # Use variant slug instead of numeric ID
        v_key = variant.slug

        if v_key in session_cart:

            if isinstance(
                session_cart[v_key],
                dict
            ):
                session_cart[v_key]["quantity"] += quantity

            else:
                session_cart[v_key] = {
                    "quantity": session_cart[v_key] + quantity
                }

        else:

            session_cart[v_key] = {
                "quantity": quantity
            }

        request.session["cart"] = session_cart
        request.session.modified = True

    messages.success(
        request,
        f"Added {variant.product.name} "
        f"({variant.sku}) to your cart."
    )

    # --------------------------------------------------------
    # REDIRECT
    # --------------------------------------------------------

    next_url = (
        request.POST.get("next")
        or request.GET.get("next")
    )

    if next_url:
        return redirect(next_url)

    return redirect("cart")


# ============================================================
# INCREASE QUANTITY
# ============================================================

def increase_quantity(request, variant_slug):

    if request.method != "POST":
        return redirect("cart")

    variant = _get_variant(variant_slug)

    if not variant:
        return redirect("cart")

    # --------------------------------------------------------
    # LOGGED-IN USER
    # --------------------------------------------------------

    if request.user.is_authenticated:

        cart_obj = Cart.objects.filter(
            user=request.user
        ).first()

        if cart_obj:

            item = CartItem.objects.filter(
                cart=cart_obj,
                product=variant
            ).first()

            if item:
                item.quantity += 1
                item.save(update_fields=["quantity"])

    # --------------------------------------------------------
    # GUEST USER
    # --------------------------------------------------------

    else:

        session_cart = request.session.get(
            "cart",
            {}
        )

        v_key = variant.slug

        if v_key in session_cart:

            if isinstance(
                session_cart[v_key],
                dict
            ):
                session_cart[v_key]["quantity"] += 1

            else:
                session_cart[v_key] = {
                    "quantity": session_cart[v_key] + 1
                }

            request.session["cart"] = session_cart
            request.session.modified = True

    return redirect("cart")


# ============================================================
# DECREASE QUANTITY
# ============================================================

def decrease_quantity(request, variant_slug):

    if request.method != "POST":
        return redirect("cart")

    variant = _get_variant(variant_slug)

    if not variant:
        return redirect("cart")

    # --------------------------------------------------------
    # LOGGED-IN USER
    # --------------------------------------------------------

    if request.user.is_authenticated:

        cart_obj = Cart.objects.filter(
            user=request.user
        ).first()

        if cart_obj:

            item = CartItem.objects.filter(
                cart=cart_obj,
                product=variant
            ).first()

            if item:

                if item.quantity > 1:

                    item.quantity -= 1
                    item.save(update_fields=["quantity"])

                else:

                    item.delete()

    # --------------------------------------------------------
    # GUEST USER
    # --------------------------------------------------------

    else:

        session_cart = request.session.get(
            "cart",
            {}
        )

        v_key = variant.slug

        if v_key in session_cart:

            if isinstance(
                session_cart[v_key],
                dict
            ):
                current_qty = session_cart[v_key].get(
                    "quantity",
                    1
                )
            else:
                current_qty = session_cart[v_key]

            try:
                current_qty = int(current_qty)
            except (ValueError, TypeError):
                current_qty = 1

            if current_qty > 1:

                if isinstance(
                    session_cart[v_key],
                    dict
                ):
                    session_cart[v_key]["quantity"] -= 1

                else:
                    session_cart[v_key] = current_qty - 1

            else:

                del session_cart[v_key]

            request.session["cart"] = session_cart
            request.session.modified = True

    return redirect("cart")


# ============================================================
# REMOVE FROM CART
# ============================================================

def remove_from_cart(request, variant_slug):

    if request.method != "POST":
        return redirect("cart")

    variant = _get_variant(variant_slug)

    if not variant:
        return redirect("cart")

    # --------------------------------------------------------
    # LOGGED-IN USER
    # --------------------------------------------------------

    if request.user.is_authenticated:

        cart_obj = Cart.objects.filter(
            user=request.user
        ).first()

        if cart_obj:

            CartItem.objects.filter(
                cart=cart_obj,
                product=variant
            ).delete()

    # --------------------------------------------------------
    # GUEST USER
    # --------------------------------------------------------

    else:

        session_cart = request.session.get(
            "cart",
            {}
        )

        v_key = variant.slug

        if v_key in session_cart:

            del session_cart[v_key]

            request.session["cart"] = session_cart
            request.session.modified = True

    messages.info(
        request,
        "Item removed from cart."
    )

    return redirect("cart")


# ============================================================
# CLEAR CART
# ============================================================

def clear_cart(request):

    if request.method != "POST":
        return redirect("cart")

    # --------------------------------------------------------
    # LOGGED-IN USER
    # --------------------------------------------------------

    if request.user.is_authenticated:

        cart_obj = Cart.objects.filter(
            user=request.user
        ).first()

        if cart_obj:
            cart_obj.items.all().delete()

    # --------------------------------------------------------
    # GUEST USER
    # --------------------------------------------------------

    else:

        request.session["cart"] = {}
        request.session.modified = True

    messages.info(
        request,
        "Your cart has been cleared."
    )

    return redirect("cart")