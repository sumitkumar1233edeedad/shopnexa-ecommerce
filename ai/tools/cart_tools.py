"""
Legacy alias module for backward compatibility.
All cart tools are implemented in ai.tools.cart.
"""
from .cart import (
    _resolve_variant,
    get_cart,
    add_to_cart,
    remove_from_cart,
    update_cart,
)

__all__ = [
    "_resolve_variant",
    "get_cart",
    "add_to_cart",
    "remove_from_cart",
    "update_cart",
]
