from decimal import Decimal
from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny

from apps.cart.models import Cart, CartItem
from apps.products.models import Product, ProductVariant
from .serializers import CartSerializer, CartItemSerializer, CartActionSerializer

try:
    from apps.coupons.services import (
        validate_coupon_for_user,
        get_available_coupons,
        get_best_coupon_for_user,
        get_user_weekly_coupon_info,
    )
except ImportError:
    validate_coupon_for_user = None
    get_available_coupons = None
    get_best_coupon_for_user = None
    get_user_weekly_coupon_info = None


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def _get_variant(variant_slug):
    """
    Find active ProductVariant by slug, or fallback to Product default variant.
    """
    variant = (
        ProductVariant.objects
        .select_related("product", "color", "stock")
        .filter(slug=str(variant_slug), is_active=True)
        .first()
    )
    if variant:
        return variant

    product = Product.objects.filter(slug=str(variant_slug), is_active=True).first()
    if product and product.default_variant:
        return product.default_variant

    return None


def _calculate_cart_totals(request, subtotal_dec):
    """
    Calculate shipping fee, coupon discount, and grand total.
    """
    applied_code = request.session.get("applied_coupon_code")
    applied_coupon_data = None
    discount_amount = Decimal("0.00")

    if request.user.is_authenticated and applied_code and validate_coupon_for_user:
        is_valid, _, coupon, discount = validate_coupon_for_user(
            applied_code,
            request.user,
            subtotal_dec
        )
        if is_valid:
            applied_coupon_data = {
                "code": coupon.code,
                "discount_type": getattr(coupon, "discount_type", "fixed"),
                "discount_value": str(getattr(coupon, "discount_value", discount)),
            }
            discount_amount = discount
        else:
            request.session.pop("applied_coupon_code", None)

    discounted_subtotal = max(Decimal("0.00"), subtotal_dec - discount_amount)
    shipping_fee = (
        Decimal("0.00")
        if (subtotal_dec >= 500 or subtotal_dec == Decimal("0.00"))
        else Decimal("50.00")
    )
    grand_total = discounted_subtotal + shipping_fee

    return {
        "subtotal": str(subtotal_dec),
        "discount_amount": str(discount_amount),
        "applied_coupon": applied_coupon_data,
        "shipping_fee": str(shipping_fee),
        "grand_total": str(grand_total),
    }


def _get_cart_response_data(request):
    """
    Generates unified cart data for both authenticated users and guests.
    """
    items_data = []
    subtotal = Decimal("0.00")

    # 1. Logged-in user: database cart
    if request.user.is_authenticated:
        cart_obj, _ = Cart.objects.get_or_create(user=request.user)
        db_items = (
            cart_obj.items
            .select_related("product__product", "product__color", "product__stock")
            .all()
        )
        items_data = CartItemSerializer(db_items, many=True, context={"request": request}).data
        subtotal = Decimal(str(cart_obj.total_price))
        total_items = cart_obj.total_items
        cart_slug = cart_obj.slug

    # 2. Guest user: session cart
    else:
        session_cart = request.session.get("cart", {})
        total_items = 0

        for variant_slug, data in list(session_cart.items()):
            variant = _get_variant(variant_slug)
            if not variant:
                del session_cart[variant_slug]
                request.session.modified = True
                continue

            qty = data.get("quantity", 1) if isinstance(data, dict) else data
            try:
                qty = int(qty)
            except (ValueError, TypeError):
                qty = 1

            if qty < 1:
                del session_cart[variant_slug]
                request.session.modified = True
                continue

            line_total = variant.price * qty
            subtotal += line_total
            total_items += qty

            img = getattr(variant.product, "image", None)
            image_url = None
            if img:
                try:
                    image_url = request.build_absolute_uri(img.url)
                except Exception:
                    image_url = getattr(img, "url", None)

            items_data.append({
                "id": None,
                "slug": variant.slug,
                "quantity": qty,
                "price": str(variant.price),
                "total_price": str(line_total),
                "product_name": variant.product.name,
                "product_slug": variant.product.slug,
                "variant_name": variant.name,
                "variant_slug": variant.slug,
                "brand": variant.product.brand,
                "color": variant.color.name if variant.color else None,
                "color_hex": variant.color.hex_code if variant.color else None,
                "size": variant.size,
                "image": image_url,
            })

        cart_slug = "guest-cart"

    totals = _calculate_cart_totals(request, subtotal)

    return {
        "success": True,
        "cart": {
            "slug": cart_slug,
            "total_items": total_items,
            "subtotal": totals["subtotal"],
            "discount_amount": totals["discount_amount"],
            "applied_coupon": totals["applied_coupon"],
            "shipping_fee": totals["shipping_fee"],
            "grand_total": totals["grand_total"],
            "items": items_data,
        }
    }


# ============================================================
# 1. CART API VIEW (COLLECTION LEVEL: GET, POST, DELETE)
# ============================================================

class CartAPIView(APIView):
    """
    Unified Cart API (Collection level)
    - GET: View cart details, items, shipping, discounts
    - POST: Add item to cart
    - DELETE: Clear all items in cart
    """
    permission_classes = [AllowAny]

    def get(self, request):
        data = _get_cart_response_data(request)
        return Response(data, status=status.HTTP_200_OK)

    def post(self, request):
        
        variant_slug = (
            request.data.get("variant_slug")
            or request.data.get("slug")
            or request.query_params.get("variant_slug")
        )
        if not variant_slug:
            return Response(
                {"success": False, "message": "variant_slug is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        variant = _get_variant(variant_slug)
        if not variant:
            return Response(
                {"success": False, "message": "Product or variant not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        # Quantity validation
        try:
            quantity = int(request.data.get("quantity", 1))
            if quantity < 1:
                quantity = 1
        except (ValueError, TypeError):
            quantity = 1

        # Stock check
        if hasattr(variant, "stock") and variant.stock:
            if variant.stock.available_quantity < quantity:
                return Response(
                    {"success": False, "message": f"Only {variant.stock.available_quantity} units available in stock."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # 1. Logged-in user
        if request.user.is_authenticated:
            cart_obj, _ = Cart.objects.get_or_create(user=request.user)
            item, created = CartItem.objects.get_or_create(
                cart=cart_obj,
                product=variant,
                defaults={"quantity": quantity}
            )
            if not created:
                item.quantity += quantity
                item.save(update_fields=["quantity"])

        # 2. Guest user
        else:
            session_cart = request.session.get("cart", {})
            v_key = variant.slug
            if v_key in session_cart:
                if isinstance(session_cart[v_key], dict):
                    session_cart[v_key]["quantity"] += quantity
                else:
                    session_cart[v_key] = {"quantity": session_cart[v_key] + quantity}
            else:
                session_cart[v_key] = {"quantity": quantity}

            request.session["cart"] = session_cart
            request.session.modified = True

        data = _get_cart_response_data(request)
        data["message"] = f"Added {variant.product.name} ({variant.sku}) to cart."
        return Response(data, status=status.HTTP_201_CREATED)

    def delete(self, request):
        if request.user.is_authenticated:
            cart_obj = Cart.objects.filter(user=request.user).first()
            if cart_obj:
                cart_obj.items.all().delete()
        else:
            request.session["cart"] = {}
            request.session.modified = True

        data = _get_cart_response_data(request)
        data["message"] = "Cart cleared successfully."
        return Response(data, status=status.HTTP_200_OK)


# ============================================================
# 2. CART ITEM API VIEW (ITEM LEVEL: PATCH, DELETE)
# ============================================================

class CartItemAPIView(APIView):
     
    permission_classes = [AllowAny]

    def patch(self, request, variant_slug):
        variant = _get_variant(variant_slug)
        if not variant:
            return Response(
                {"success": False, "message": "Product or variant not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        action = request.data.get("action")
        target_qty = request.data.get("quantity")

        if not action and target_qty is None:
            return Response(
                {"success": False, "message": "Provide 'action' ('increase'/'decrease') or 'quantity'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 1. Logged-in user
        if request.user.is_authenticated:
            cart_obj = Cart.objects.filter(user=request.user).first()
            if not cart_obj:
                return Response({"success": False, "message": "Cart is empty."}, status=status.HTTP_404_NOT_FOUND)

            item = CartItem.objects.filter(cart=cart_obj, product=variant).first()
            if not item:
                return Response({"success": False, "message": "Item not in cart."}, status=status.HTTP_404_NOT_FOUND)

            if action == "increase":
                item.quantity += 1
                item.save(update_fields=["quantity"])
            elif action == "decrease":
                if item.quantity > 1:
                    item.quantity -= 1
                    item.save(update_fields=["quantity"])
                else:
                    item.delete()
            elif target_qty is not None:
                try:
                    qty = int(target_qty)
                    if qty > 0:
                        item.quantity = qty
                        item.save(update_fields=["quantity"])
                    else:
                        item.delete()
                except (ValueError, TypeError):
                    return Response({"success": False, "message": "Invalid quantity."}, status=status.HTTP_400_BAD_REQUEST)

        # 2. Guest user
        else:
            session_cart = request.session.get("cart", {})
            v_key = variant.slug
            if v_key not in session_cart:
                return Response({"success": False, "message": "Item not in cart."}, status=status.HTTP_404_NOT_FOUND)

            current_qty = session_cart[v_key].get("quantity", 1) if isinstance(session_cart[v_key], dict) else session_cart[v_key]
            try:
                current_qty = int(current_qty)
            except (ValueError, TypeError):
                current_qty = 1

            if action == "increase":
                session_cart[v_key] = {"quantity": current_qty + 1}
            elif action == "decrease":
                if current_qty > 1:
                    session_cart[v_key] = {"quantity": current_qty - 1}
                else:
                    del session_cart[v_key]
            elif target_qty is not None:
                try:
                    qty = int(target_qty)
                    if qty > 0:
                        session_cart[v_key] = {"quantity": qty}
                    else:
                        del session_cart[v_key]
                except (ValueError, TypeError):
                    return Response({"success": False, "message": "Invalid quantity."}, status=status.HTTP_400_BAD_REQUEST)

            request.session["cart"] = session_cart
            request.session.modified = True

        data = _get_cart_response_data(request)
        data["message"] = "Cart updated successfully."
        return Response(data, status=status.HTTP_200_OK)

    def delete(self, request, variant_slug):
        variant = _get_variant(variant_slug)
        if not variant:
            return Response(
                {"success": False, "message": "Product or variant not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        # 1. Logged-in user
        if request.user.is_authenticated:
            cart_obj = Cart.objects.filter(user=request.user).first()
            if cart_obj:
                CartItem.objects.filter(cart=cart_obj, product=variant).delete()

        # 2. Guest user
        else:
            session_cart = request.session.get("cart", {})
            if variant.slug in session_cart:
                del session_cart[variant.slug]
                request.session["cart"] = session_cart
                request.session.modified = True

        data = _get_cart_response_data(request)
        data["message"] = "Item removed from cart."
        return Response(data, status=status.HTTP_200_OK)
