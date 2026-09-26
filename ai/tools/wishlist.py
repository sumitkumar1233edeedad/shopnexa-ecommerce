import json
from langchain_core.tools import tool
from apps.accounts.models import WishList
from apps.products.models import Product, ProductVariant
from ai.context import get_current_user


def _resolve_product(product_slug: str) -> Product | None:
    """Helper to resolve a Product by product slug or variant slug."""
    if not product_slug:
        return None

    slug_str = str(product_slug).strip()
    product = Product.objects.filter(slug=slug_str, is_active=True).first()
    if product:
        return product

    variant = (
        ProductVariant.objects.filter(slug=slug_str, is_active=True)
        .select_related("product")
        .first()
    )
    if variant:
        return variant.product

    return None


@tool
def get_wishlist() -> str:
    """
    Retrieve all products currently saved in the authenticated user's wishlist.
    Returns product names, slugs, brands, prices, and stock status.
    """
    try:
        user = get_current_user()
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Authentication required: {str(e)}",
        })

    try:
        items = (
            WishList.objects.filter(user=user)
            .select_related("product")
            .prefetch_related("product__variants__stock", "product__cat")
            .all()
        )

        if not items.exists():
            return json.dumps({
                "success": True,
                "message": "Your wishlist is currently empty.",
                "count": 0,
                "items": [],
            })

        results = []
        for item in items:
            p = item.product
            results.append({
                "wishlist_slug": item.slug,
                "name": p.name,
                "slug": p.slug,
                "brand": p.brand,
                "price": str(p.price) if p.price is not None else None,
                "min_price": str(p.min_price) if p.min_price is not None else None,
                "max_price": str(p.max_price) if p.max_price is not None else None,
                "in_stock": p.in_stock,
                "categories": list(p.cat.values_list("name", flat=True)),
            })

        return json.dumps({
            "success": True,
            "count": len(results),
            "items": results,
        })
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Error retrieving wishlist: {str(e)}",
        })


@tool
def add_to_wishlist(product_slug: str) -> str:
    """
    Add a product to the authenticated user's wishlist using the product slug.
    Prevents duplicate entries.
    """
    try:
        user = get_current_user()
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Authentication required: {str(e)}",
        })

    try:
        product = _resolve_product(product_slug)
        if not product:
            return json.dumps({
                "success": False,
                "error": f"Product with slug '{product_slug}' was not found.",
            })

        existing = WishList.objects.filter(user=user, product=product).first()
        if existing:
            return json.dumps({
                "success": True,
                "message": f"'{product.name}' is already in your wishlist.",
                "product_name": product.name,
                "product_slug": product.slug,
            })

        wishlist_item = WishList.objects.create(user=user, product=product)
        return json.dumps({
            "success": True,
            "message": f"Successfully added '{product.name}' to your wishlist.",
            "product_name": product.name,
            "product_slug": product.slug,
            "wishlist_slug": wishlist_item.slug,
        })
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Error adding to wishlist: {str(e)}",
        })


@tool
def remove_from_wishlist(product_slug: str) -> str:
    """
    Remove a product from the authenticated user's wishlist using the product slug.
    """
    try:
        user = get_current_user()
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Authentication required: {str(e)}",
        })

    try:
        product = _resolve_product(product_slug)
        if not product:
            return json.dumps({
                "success": False,
                "error": f"Product with slug '{product_slug}' was not found.",
            })

        item = WishList.objects.filter(user=user, product=product).first()
        if not item:
            return json.dumps({
                "success": False,
                "error": f"'{product.name}' was not found in your wishlist.",
            })

        item.delete()
        return json.dumps({
            "success": True,
            "message": f"Removed '{product.name}' from your wishlist.",
            "product_slug": product.slug,
        })
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Error removing from wishlist: {str(e)}",
        })


@tool
def check_wishlist(product_slug: str) -> str:
    """
    Check if a specific product is currently in the authenticated user's wishlist.
    """
    try:
        user = get_current_user()
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Authentication required: {str(e)}",
        })

    try:
        product = _resolve_product(product_slug)
        if not product:
            return json.dumps({
                "success": False,
                "error": f"Product with slug '{product_slug}' was not found.",
            })

        is_wishlisted = WishList.objects.filter(user=user, product=product).exists()
        return json.dumps({
            "success": True,
            "product_name": product.name,
            "product_slug": product.slug,
            "is_in_wishlist": is_wishlisted,
        })
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Error checking wishlist: {str(e)}",
        })
