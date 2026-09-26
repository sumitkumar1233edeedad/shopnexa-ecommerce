import json
from decimal import Decimal
from django.db.models import Q
from langchain_core.tools import tool
from apps.products.models import Product, ProductVariant, Category, Stock


def _serialize_variant(variant: ProductVariant) -> dict:
    """Helper to serialize a ProductVariant with stock details."""
    stock_qty = 0
    if hasattr(variant, "stock") and variant.stock:
        stock_qty = variant.stock.available_quantity

    return {
        "variant_name": variant.name,
        "sku": variant.sku,
        "variant_slug": variant.slug,
        "color": variant.color.name if variant.color else None,
        "size": variant.size,
        "price": str(variant.price),
        "available_stock": stock_qty,
        "is_in_stock": stock_qty > 0,
    }


def _serialize_product_summary(product: Product) -> dict:
    """Helper to serialize product summary information."""
    categories = list(product.cat.values_list("name", flat=True))
    return {
        "name": product.name,
        "slug": product.slug,
        "brand": product.brand,
        "categories": categories,
        "price": str(product.price) if product.price is not None else None,
        "min_price": str(product.min_price) if product.min_price is not None else None,
        "max_price": str(product.max_price) if product.max_price is not None else None,
        "in_stock": product.in_stock,
        "average_rating": product.average_rating,
    }


@tool
def search_products(query: str) -> str:
    """
    Search products in the catalog by keyword across name, description, brand, or category name.
    Returns structured results including product name, slug, brand, categories, price range, and stock availability.
    """
    if not query or not str(query).strip():
        return json.dumps({
            "success": False,
            "error": "Search query cannot be empty.",
            "results": [],
            "count": 0,
        })

    q = str(query).strip()
    try:
        products = (
            Product.objects.filter(is_active=True)
            .filter(
                Q(name__icontains=q)
                | Q(description__icontains=q)
                | Q(brand__icontains=q)
                | Q(cat__name__icontains=q)
            )
            .distinct()
            .prefetch_related("cat", "variants__stock", "variants__color")[:10]
        )

        if not products.exists():
            return json.dumps({
                "success": True,
                "message": f"No products found matching '{query}'.",
                "results": [],
                "count": 0,
            })

        results = [_serialize_product_summary(p) for p in products]
        return json.dumps({
            "success": True,
            "count": len(results),
            "results": results,
        })
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Database error while searching products: {str(e)}",
            "results": [],
            "count": 0,
        })


@tool
def get_product_details(product_slug: str) -> str:
    """
    Retrieve comprehensive details for a specific product using its unique product slug.
    Returns name, slug, description, brand, categories, rating, and all available variants with stock and prices.
    """
    if not product_slug or not str(product_slug).strip():
        return json.dumps({
            "success": False,
            "error": "product_slug is required.",
        })

    slug_str = str(product_slug).strip()
    try:
        product = (
            Product.objects.filter(slug=slug_str, is_active=True)
            .prefetch_related("cat", "variants__stock", "variants__color")
            .first()
        )

        # Fallback: check if slug belongs to a variant
        if not product:
            variant = (
                ProductVariant.objects.filter(slug=slug_str, is_active=True)
                .select_related("product")
                .first()
            )
            if variant:
                product = variant.product

        if not product:
            return json.dumps({
                "success": False,
                "error": f"Product with slug '{product_slug}' was not found.",
            })

        active_variants = [
            _serialize_variant(v) for v in product.variants.filter(is_active=True)
        ]

        details = {
            "success": True,
            "name": product.name,
            "slug": product.slug,
            "description": product.description,
            "brand": product.brand,
            "categories": list(product.cat.values_list("name", flat=True)),
            "in_stock": product.in_stock,
            "average_rating": product.average_rating,
            "review_count": product.review_count,
            "price": str(product.price) if product.price is not None else None,
            "min_price": str(product.min_price) if product.min_price is not None else None,
            "max_price": str(product.max_price) if product.max_price is not None else None,
            "variants": active_variants,
        }
        return json.dumps(details)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Error retrieving product details: {str(e)}",
        })


@tool
def check_stock(product_slug: str) -> str:
    """
    Check real-time stock availability for a product or specific variant using its slug.
    Returns available quantity and stock status.
    """
    if not product_slug or not str(product_slug).strip():
        return json.dumps({
            "success": False,
            "error": "product_slug is required.",
        })

    slug_str = str(product_slug).strip()
    try:
        # 1. Check if it's a specific variant slug
        variant = (
            ProductVariant.objects.filter(slug=slug_str, is_active=True)
            .select_related("product", "stock")
            .first()
        )
        if variant:
            stock_qty = variant.stock.available_quantity if hasattr(variant, "stock") and variant.stock else 0
            return json.dumps({
                "success": True,
                "product_name": variant.product.name,
                "variant_name": variant.name,
                "sku": variant.sku,
                "variant_slug": variant.slug,
                "available_stock": stock_qty,
                "is_in_stock": stock_qty > 0,
            })

        # 2. Check if it's a product slug
        product = (
            Product.objects.filter(slug=slug_str, is_active=True)
            .prefetch_related("variants__stock")
            .first()
        )
        if not product:
            return json.dumps({
                "success": False,
                "error": f"Product or variant with slug '{product_slug}' not found.",
            })

        variants_stock = []
        total_stock = 0
        for v in product.variants.filter(is_active=True):
            qty = v.stock.available_quantity if hasattr(v, "stock") and v.stock else 0
            total_stock += qty
            variants_stock.append({
                "variant_name": v.name,
                "variant_slug": v.slug,
                "sku": v.sku,
                "available_stock": qty,
                "is_in_stock": qty > 0,
            })

        return json.dumps({
            "success": True,
            "product_name": product.name,
            "product_slug": product.slug,
            "total_available_stock": total_stock,
            "is_in_stock": total_stock > 0,
            "variants": variants_stock,
        })
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Error checking stock: {str(e)}",
        })


@tool
def get_product_price(product_slug: str) -> str:
    """
    Get current price information for a product or specific variant using its slug.
    Returns price, min_price, and max_price.
    """
    if not product_slug or not str(product_slug).strip():
        return json.dumps({
            "success": False,
            "error": "product_slug is required.",
        })

    slug_str = str(product_slug).strip()
    try:
        # Check variant first
        variant = (
            ProductVariant.objects.filter(slug=slug_str, is_active=True)
            .select_related("product")
            .first()
        )
        if variant:
            return json.dumps({
                "success": True,
                "product_name": variant.product.name,
                "variant_name": variant.name,
                "variant_slug": variant.slug,
                "price": str(variant.price),
                "currency": "INR",
            })

        product = (
            Product.objects.filter(slug=slug_str, is_active=True)
            .prefetch_related("variants")
            .first()
        )
        if not product:
            return json.dumps({
                "success": False,
                "error": f"Product or variant with slug '{product_slug}' not found.",
            })

        return json.dumps({
            "success": True,
            "product_name": product.name,
            "product_slug": product.slug,
            "price": str(product.price) if product.price is not None else None,
            "min_price": str(product.min_price) if product.min_price is not None else None,
            "max_price": str(product.max_price) if product.max_price is not None else None,
            "currency": "INR",
        })
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Error retrieving price: {str(e)}",
        })


@tool
def search_category(category_name: str) -> str:
    """
    Search for products within a specific category name or slug.
    Returns structured list of products belonging to the category.
    """
    if not category_name or not str(category_name).strip():
        return json.dumps({
            "success": False,
            "error": "category_name is required.",
        })

    c_name = str(category_name).strip()
    try:
        category = Category.objects.filter(
            Q(name__icontains=c_name) | Q(slug__iexact=c_name)
        ).first()

        if not category:
            return json.dumps({
                "success": True,
                "message": f"Category '{category_name}' not found.",
                "results": [],
                "count": 0,
            })

        products = (
            category.product.filter(is_active=True)
            .distinct()
            .prefetch_related("cat", "variants__stock", "variants__color")[:10]
        )

        results = [_serialize_product_summary(p) for p in products]
        return json.dumps({
            "success": True,
            "category": category.name,
            "category_slug": category.slug,
            "count": len(results),
            "results": results,
        })
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Error searching category: {str(e)}",
        })


@tool
def search_by_brand(brand: str) -> str:
    """
    Search for active products manufactured by a specific brand.
    Returns structured list of products for the brand.
    """
    if not brand or not str(brand).strip():
        return json.dumps({
            "success": False,
            "error": "brand is required.",
        })

    b_name = str(brand).strip()
    try:
        products = (
            Product.objects.filter(brand__icontains=b_name, is_active=True)
            .distinct()
            .prefetch_related("cat", "variants__stock", "variants__color")[:10]
        )

        if not products.exists():
            return json.dumps({
                "success": True,
                "message": f"No products found for brand '{brand}'.",
                "results": [],
                "count": 0,
            })

        results = [_serialize_product_summary(p) for p in products]
        return json.dumps({
            "success": True,
            "brand": brand,
            "count": len(results),
            "results": results,
        })
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Error searching brand: {str(e)}",
        })


@tool
def search_by_price(min_price: float = 0.0, max_price: float = None) -> str:
    """
    Filter products based on actual ProductVariant price range.
    min_price: minimum price (default 0.0)
    max_price: maximum price (optional)
    """
    try:
        min_p = Decimal(str(min_price)) if min_price is not None else Decimal("0.00")
    except Exception:
        min_p = Decimal("0.00")

    filters = Q(is_active=True) & Q(variants__is_active=True) & Q(variants__price__gte=min_p)

    if max_price is not None:
        try:
            max_p = Decimal(str(max_price))
            filters &= Q(variants__price__lte=max_p)
        except Exception:
            pass

    try:
        products = (
            Product.objects.filter(filters)
            .distinct()
            .prefetch_related("cat", "variants__stock", "variants__color")[:10]
        )

        if not products.exists():
            return json.dumps({
                "success": True,
                "message": "No products found within the specified price range.",
                "results": [],
                "count": 0,
            })

        results = [_serialize_product_summary(p) for p in products]
        return json.dumps({
            "success": True,
            "min_price": str(min_p),
            "max_price": str(max_price) if max_price is not None else None,
            "count": len(results),
            "results": results,
        })
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Error searching by price: {str(e)}",
        })
