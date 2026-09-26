"""
Legacy alias module for backward compatibility.
All order tools are implemented in ai.tools.orders.
"""
from .orders import (
    _serialize_order_summary,
    get_orders,
    get_order_details,
    get_order_status,
)

__all__ = [
    "_serialize_order_summary",
    "get_orders",
    "get_order_details",
    "get_order_status",
]
