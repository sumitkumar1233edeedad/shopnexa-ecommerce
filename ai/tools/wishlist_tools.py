"""
Legacy alias module for backward compatibility.
All wishlist tools are implemented in ai.tools.wishlist.
"""
from .wishlist import (
    _resolve_product,
    get_wishlist,
    add_to_wishlist,
    remove_from_wishlist,
    check_wishlist,
)

__all__ = [
    "_resolve_product",
    "get_wishlist",
    "add_to_wishlist",
    "remove_from_wishlist",
    "check_wishlist",
]
