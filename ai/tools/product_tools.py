"""
Legacy alias module for backward compatibility.
All product tools are implemented in ai.tools.products.
"""
from .products import (
    _serialize_variant,
    _serialize_product_summary,
    search_products,
    get_product_details,
    check_stock,
    get_product_price,
    search_category,
    search_by_brand,
    search_by_price,
)

__all__ = [
    "_serialize_variant",
    "_serialize_product_summary",
    "search_products",
    "get_product_details",
    "check_stock",
    "get_product_price",
    "search_category",
    "search_by_brand",
    "search_by_price",
]
