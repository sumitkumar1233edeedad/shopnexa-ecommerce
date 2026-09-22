from django.urls import path
from .views import OrderListCreateAPIView, OrderDetailAPIView, OrderCancelAPIView

urlpatterns = [
    # List all user orders & create new order from cart
    path("orders/", OrderListCreateAPIView.as_view(), name="api_order_list_create"),

    # Retrieve order details by order_number or slug
    path("orders/<str:identifier>/", OrderDetailAPIView.as_view(), name="api_order_detail"),

    # Cancel order by order_number or slug
    path("orders/<str:identifier>/cancel/", OrderCancelAPIView.as_view(), name="api_order_cancel"),
]
