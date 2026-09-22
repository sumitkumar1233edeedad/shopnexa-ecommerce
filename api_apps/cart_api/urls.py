from django.urls import path
from .views import CartAPIView, CartItemAPIView

urlpatterns = [
    # Cart Collection: View cart, Add item, Clear cart
    path("cart/", CartAPIView.as_view(), name="api_cart"),

    # Cart Item: Increase, Decrease, Update quantity, Remove item
    path("cart/items/<slug:variant_slug>/", CartItemAPIView.as_view(), name="api_cart_item"),
]
