from django.urls import path
from . import views

app_name = "coupons"

urlpatterns = [
    path("", views.public_coupon_list_view, name="coupon_list"),
    path("apply/", views.apply_coupon_view, name="apply_coupon"),
    path("remove/", views.remove_coupon_view, name="remove_coupon"),
]
