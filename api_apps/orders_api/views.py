from django.db import transaction
from django.db.models import Q
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.order.models import Order
from .serializers import OrderSerializer, OrderCreateSerializer


# ============================================================
# 1. ORDER LIST & CREATE API VIEW (COLLECTION LEVEL)
# ============================================================
class OrderListCreateAPIView(APIView):
    """
    GET  /api/orders/ -> List user's orders (supports ?status=)
    POST /api/orders/ -> Place a new order from active Cart
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        orders = (
            Order.objects.filter(user=request.user)
            .select_related("coupon")
            .prefetch_related(
                "items__variant__product",
                "items__variant__color"
            )
            .order_by("-created_at")
        )

        status_filter = request.query_params.get("status", "").strip()
        if status_filter:
            orders = orders.filter(status=status_filter)

        serializer = OrderSerializer(orders, many=True, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        create_serializer = OrderCreateSerializer(
            data=request.data,
            context={"request": request}
        )
        create_serializer.is_valid(raise_exception=True)
        order = create_serializer.save()

        return Response(
            OrderSerializer(order, context={"request": request}).data,
            status=status.HTTP_201_CREATED
        )


# ============================================================
# 2. ORDER DETAIL API VIEW (DETAIL LEVEL)
# ============================================================
class OrderDetailAPIView(APIView):
    """
    GET /api/orders/<identifier>/ -> Retrieve order details by order_number or slug
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, identifier):
        order = (
            Order.objects.filter(user=request.user)
            .filter(Q(order_number=identifier) | Q(slug=identifier))
            .select_related("coupon")
            .prefetch_related(
                "items__variant__product",
                "items__variant__color"
            )
            .first()
        )

        if not order:
            return Response(
                {"error": "Order not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = OrderSerializer(order, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)


# ============================================================
# 3. ORDER CANCEL API VIEW (ACTION LEVEL)
# ============================================================
class OrderCancelAPIView(APIView):
    """
    POST /api/orders/<identifier>/cancel/ -> Cancel an order and restore stock if COD
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, identifier):
        order = (
            Order.objects.filter(user=request.user)
            .filter(Q(order_number=identifier) | Q(slug=identifier))
            .prefetch_related("items__variant__stock")
            .first()
        )

        if not order:
            return Response(
                {"error": "Order not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        if order.status in ["shipped", "delivered", "cancelled"]:
            return Response(
                {"error": f"Cannot cancel order with current status '{order.get_status_display()}'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            # If stock was deducted (e.g. COD pending order), restore it
            if order.status in ["pending", "confirmed"]:
                for item in order.items.all():
                    if hasattr(item.variant, "stock") and item.variant.stock:
                        stock = item.variant.stock
                        stock.quantity += item.quantity
                        stock.save(update_fields=["quantity"])

            order.status = "cancelled"
            order.save(update_fields=["status"])

        return Response(
            {
                "success": True,
                "message": "Order has been cancelled successfully.",
                "order_number": order.order_number,
                "status": order.status,
            },
            status=status.HTTP_200_OK
        )
