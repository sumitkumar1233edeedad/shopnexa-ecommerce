import json
from django.db.models import Q
from langchain_core.tools import tool
from apps.cart.models import Cart, CartItem
from apps.products.models import Product, ProductVariant
from ai.context import get_current_user


def _resolve_variant(product_slug: str) -> ProductVariant | None:
    """
    Resolve active ProductVariant by variant slug or product slug (default variant).
    """
    if not product_slug:
        return None

    slug_str = str(product_slug).strip()

    # 1. Search by ProductVariant slug
    variant = (
        ProductVariant.objects.filter(slug=slug_str, is_active=True)
        .select_related("product", "color", "stock")
        .first()
    )
    if variant:
        return variant

    # 2. Search by Product slug -> default variant
    product = (
        Product.objects.filter(slug=slug_str, is_active=True)
        .prefetch_related("variants__stock", "variants__color")
        .first()
    )
    if product and product.default_variant:
        return product.default_variant

    return None


@tool
def get_cart() -> str:
    """
    Retrieve the current authenticated user's shopping cart.
    Returns all items currently in cart, quantities, unit prices, line totals, and grand total.
    """
    try:
        user = get_current_user()
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Authentication required: {str(e)}",
        })

    try:
        cart, _ = Cart.objects.get_or_create(user=user)
        items = (
            cart.items.select_related("product__product", "product__color", "product__stock")
            .all()
        )

        if not items.exists():
            return json.dumps({
                "success": True,
                "message": "Your cart is currently empty.",
                "total_items": 0,
                "total_price": "0.00",
                "items": [],
            })

        items_data = []
        for item in items:
            v = item.product
            stock_qty = v.stock.available_quantity if hasattr(v, "stock") and v.stock else 0
            items_data.append({
                "item_slug": item.slug,
                "product_name": v.product.name,
                "product_slug": v.product.slug,
                "variant_name": v.name,
                "variant_slug": v.slug,
                "sku": v.sku,
                "quantity": item.quantity,
                "price": str(v.price),
                "total_price": str(item.total_price),
                "available_stock": stock_qty,
            })

        return json.dumps({
            "success": True,
            "total_items": cart.total_items,
            "total_price": str(cart.total_price),
            "items": items_data,
        })
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Error retrieving cart: {str(e)}",
        })


@tool
def add_to_cart(product_slug: str, quantity: int = 1) -> str:
    """
    Add a product or variant to the authenticated user's shopping cart using its slug.
    Validates available stock before adding.
    product_slug: Product or variant slug.
    quantity: Positive integer quantity to add (default 1).
    """
    try:
        user = get_current_user()
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Authentication required: {str(e)}",
        })

    try:
        qty = int(quantity)
        if qty < 1:
            qty = 1
    except (ValueError, TypeError):
        qty = 1

    try:
        variant = _resolve_variant(product_slug)
        if not variant:
            return json.dumps({
                "success": False,
                "error": f"Product or variant with slug '{product_slug}' was not found.",
            })

        # Stock validation
        stock_qty = variant.stock.available_quantity if hasattr(variant, "stock") and variant.stock else 0
        if stock_qty <= 0:
            return json.dumps({
                "success": False,
                "error": f"Sorry, '{variant.name}' is currently out of stock.",
                "available_stock": 0,
            })

        cart, _ = Cart.objects.get_or_create(user=user)
        cart_item = CartItem.objects.filter(cart=cart, product=variant).first()

        existing_qty = cart_item.quantity if cart_item else 0
        new_qty = existing_qty + qty

        if new_qty > stock_qty:
            return json.dumps({
                "success": False,
                "error": f"Cannot add {qty} items. Only {stock_qty} units available in stock (you already have {existing_qty} in your cart).",
                "available_stock": stock_qty,
                "current_cart_quantity": existing_qty,
            })

        if cart_item:
            cart_item.quantity = new_qty
            cart_item.save(update_fields=["quantity"])
        else:
            CartItem.objects.create(cart=cart, product=variant, quantity=qty)

        return json.dumps({
            "success": True,
            "message": f"Successfully added {qty} unit(s) of '{variant.name}' to your cart.",
            "product_name": variant.product.name,
            "variant_slug": variant.slug,
            "cart_quantity": new_qty,
            "unit_price": str(variant.price),
            "cart_total_items": cart.total_items,
            "cart_total_price": str(cart.total_price),
        })
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Error adding to cart: {str(e)}",
        })


@tool
def remove_from_cart(product_slug: str) -> str:
    """
    Remove an item completely from the authenticated user's cart using the product or variant slug.
    """
    try:
        user = get_current_user()
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Authentication required: {str(e)}",
        })

    try:
        cart = Cart.objects.filter(user=user).first()
        if not cart:
            return json.dumps({
                "success": False,
                "error": "Your cart is empty.",
            })

        variant = _resolve_variant(product_slug)
        slug_str = str(product_slug).strip()

        cart_item = None
        if variant:
            cart_item = CartItem.objects.filter(cart=cart, product=variant).first()

        if not cart_item:
            cart_item = CartItem.objects.filter(cart=cart).filter(
                Q(product__slug=slug_str)
                | Q(product__product__slug=slug_str)
                | Q(slug=slug_str)
            ).first()

        if not cart_item:
            return json.dumps({
                "success": False,
                "error": f"Item '{product_slug}' was not found in your cart.",
            })

        item_name = cart_item.product.name
        cart_item.delete()

        return json.dumps({
            "success": True,
            "message": f"Removed '{item_name}' from your cart.",
            "cart_total_items": cart.total_items,
            "cart_total_price": str(cart.total_price),
        })
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Error removing from cart: {str(e)}",
        })


@tool
def update_cart(product_slug: str, quantity: int) -> str:
    """
    Update the quantity of an existing item in the authenticated user's cart.
    If quantity <= 0, the item is removed from the cart.
    Checks stock availability before updating.
    """
    try:
        user = get_current_user()
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Authentication required: {str(e)}",
        })

    try:
        target_qty = int(quantity)
    except (ValueError, TypeError):
        return json.dumps({
            "success": False,
            "error": "Invalid quantity provided.",
        })

    try:
        cart = Cart.objects.filter(user=user).first()
        if not cart:
            return json.dumps({
                "success": False,
                "error": "Your cart is empty.",
            })

        variant = _resolve_variant(product_slug)
        slug_str = str(product_slug).strip()

        cart_item = None
        if variant:
            cart_item = CartItem.objects.filter(cart=cart, product=variant).first()

        if not cart_item:
            cart_item = CartItem.objects.filter(cart=cart).filter(
                Q(product__slug=slug_str)
                | Q(product__product__slug=slug_str)
                | Q(slug=slug_str)
            ).first()

        if not cart_item:
            return json.dumps({
                "success": False,
                "error": f"Item '{product_slug}' is not in your cart.",
            })

        if target_qty <= 0:
            item_name = cart_item.product.name
            cart_item.delete()
            return json.dumps({
                "success": True,
                "message": f"Removed '{item_name}' from your cart as quantity was set to {target_qty}.",
                "cart_total_items": cart.total_items,
                "cart_total_price": str(cart.total_price),
            })

        # Validate stock
        v = cart_item.product
        stock_qty = v.stock.available_quantity if hasattr(v, "stock") and v.stock else 0
        if target_qty > stock_qty:
            return json.dumps({
                "success": False,
                "error": f"Cannot update to {target_qty} units. Only {stock_qty} available in stock.",
                "available_stock": stock_qty,
                "current_cart_quantity": cart_item.quantity,
            })

        cart_item.quantity = target_qty
        cart_item.save(update_fields=["quantity"])

        return json.dumps({
            "success": True,
            "message": f"Updated quantity of '{v.name}' to {target_qty}.",
            "product_name": v.product.name,
            "variant_slug": v.slug,
            "quantity": target_qty,
            "cart_total_items": cart.total_items,
            "cart_total_price": str(cart.total_price),
        })
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Error updating cart: {str(e)}",
        })
