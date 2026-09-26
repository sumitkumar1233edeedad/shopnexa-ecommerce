from .products import (
    search_products,
    get_product_details,
    check_stock,
    get_product_price,
    search_category,
    search_by_brand,
    search_by_price,
)
from .cart import (
    get_cart,
    add_to_cart,
    remove_from_cart,
    update_cart,
)
from .wishlist import (
    get_wishlist,
    add_to_wishlist,
    remove_from_wishlist,
    check_wishlist,
)
from .orders import (
    get_orders,
    get_order_details,
    get_order_status,
)

ALL_TOOLS = [
    # Product tools
    search_products,
    get_product_details,
    check_stock,
    get_product_price,
    search_category,
    search_by_brand,
    search_by_price,

    # Cart tools
    get_cart,
    add_to_cart,
    remove_from_cart,
    update_cart,

    # Wishlist tools
    get_wishlist,
    add_to_wishlist,
    remove_from_wishlist,
    check_wishlist,

    # Order tools
    get_orders,
    get_order_details,
    get_order_status,
]

TOOL_MAP = {tool.name: tool for tool in ALL_TOOLS}

__all__ = [
    "ALL_TOOLS",
    "TOOL_MAP",
    "search_products",
    "get_product_details",
    "check_stock",
    "get_product_price",
    "search_category",
    "search_by_brand",
    "search_by_price",
    "get_cart",
    "add_to_cart",
    "remove_from_cart",
    "update_cart",
    "get_wishlist",
    "add_to_wishlist",
    "remove_from_wishlist",
    "check_wishlist",
    "get_orders",
    "get_order_details",
    "get_order_status",
]
