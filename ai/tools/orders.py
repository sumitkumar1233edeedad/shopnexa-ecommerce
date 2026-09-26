import json
from django.db.models import Q
from langchain_core.tools import tool
from apps.order.models import Order
from ai.context import get_current_user


def _serialize_order_summary(order: Order) -> dict:
    """Helper to serialize an order summary."""
    return {
        "order_number": order.order_number,
        "order_slug": order.slug,
        "status": order.get_status_display() if hasattr(order, "get_status_display") else order.status,
        "raw_status": order.status,
        "total_amount": str(order.total),
        "total_items": order.total_items,
        "created_at": order.created_at.strftime("%Y-%m-%d %H:%M:%S") if order.created_at else None,
    }


@tool
def get_orders() -> str:
    """
    Retrieve the authenticated user's order history.
    Lists all past orders, their order numbers, statuses, total amounts, and dates.
    Never exposes orders belonging to other users.
    """
    try:
        user = get_current_user()
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Authentication required: {str(e)}",
        })

    try:
        orders = (
            Order.objects.filter(user=user)
            .prefetch_related("items")
            .order_by("-created_at")[:10]
        )

        if not orders.exists():
            return json.dumps({
                "success": True,
                "message": "You have not placed any orders yet.",
                "count": 0,
                "orders": [],
            })

        results = [_serialize_order_summary(o) for o in orders]
        return json.dumps({
            "success": True,
            "count": len(results),
            "orders": results,
        })
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Error retrieving orders: {str(e)}",
        })


@tool
def get_order_details(order_identifier: str) -> str:
    """
    Retrieve detailed information for a specific order using its order number or slug.
    Strictly scoped to the authenticated user to prevent IDOR access.
    Returns items purchased, quantities, pricing breakdown, shipping details, and status.
    """
    try:
        user = get_current_user()
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Authentication required: {str(e)}",
        })

    if not order_identifier or not str(order_identifier).strip():
        return json.dumps({
            "success": False,
            "error": "order_identifier is required.",
        })

    identifier = str(order_identifier).strip()

    try:
        # Query strictly scoped to current user
        order = (
            Order.objects.filter(user=user)
            .filter(Q(order_number__iexact=identifier) | Q(slug__iexact=identifier))
            .prefetch_related("items__variant__product", "items__variant__color")
            .first()
        )

        if not order:
            # Check if this order exists for another user to flag unauthorized IDOR attempt
            exists_elsewhere = Order.objects.filter(
                Q(order_number__iexact=identifier) | Q(slug__iexact=identifier)
            ).exists()
            if exists_elsewhere:
                return json.dumps({
                    "success": False,
                    "error": "Unauthorized access: You do not have permission to view this order.",
                    "authorized": False,
                })
            return json.dumps({
                "success": False,
                "error": f"Order '{order_identifier}' was not found.",
            })

        items_data = []
        for item in order.items.all():
            v = item.variant
            items_data.append({
                "item_name": v.product.name if v.product else v.sku,
                "variant_name": v.name,
                "sku": v.sku,
                "quantity": item.quantity,
                "price": str(item.price),
                "subtotal": str(item.subtotal),
            })

        return json.dumps({
            "success": True,
            "order_number": order.order_number,
            "order_slug": order.slug,
            "status": order.get_status_display() if hasattr(order, "get_status_display") else order.status,
            "raw_status": order.status,
            "total_amount": str(order.total),
            "discount_amount": str(order.discount_amount),
            "total_items": order.total_items,
            "shipping_details": {
                "name": order.shipping_name,
                "phone": order.shipping_phone,
                "city": order.shipping_city,
                "pincode": order.shipping_pincode,
                "address": order.shipping_address,
            },
            "items": items_data,
            "created_at": order.created_at.strftime("%Y-%m-%d %H:%M:%S") if order.created_at else None,
        })
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Error retrieving order details: {str(e)}",
        })


@tool
def get_order_status(order_identifier: str) -> str:
    """
    Check the current fulfillment and shipment status of a specific order.
    Strictly scoped to the authenticated user.
    """
    try:
        user = get_current_user()
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Authentication required: {str(e)}",
        })

    if not order_identifier or not str(order_identifier).strip():
        return json.dumps({
            "success": False,
            "error": "order_identifier is required.",
        })

    identifier = str(order_identifier).strip()

    try:
        order = (
            Order.objects.filter(user=user)
            .filter(Q(order_number__iexact=identifier) | Q(slug__iexact=identifier))
            .first()
        )

        if not order:
            exists_elsewhere = Order.objects.filter(
                Q(order_number__iexact=identifier) | Q(slug__iexact=identifier)
            ).exists()
            if exists_elsewhere:
                return json.dumps({
                    "success": False,
                    "error": "Unauthorized access: You do not have permission to view this order.",
                    "authorized": False,
                })
            return json.dumps({
                "success": False,
                "error": f"Order '{order_identifier}' was not found.",
            })

        return json.dumps({
            "success": True,
            "order_number": order.order_number,
            "status": order.get_status_display() if hasattr(order, "get_status_display") else order.status,
            "raw_status": order.status,
            "updated_at": order.updated_at.strftime("%Y-%m-%d %H:%M:%S") if order.updated_at else None,
        })
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Error retrieving order status: {str(e)}",
        })
