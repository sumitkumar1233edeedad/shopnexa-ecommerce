from django.urls import path
from .views import (
    CouponListAPIView,
    CouponDetailAPIView,
    CouponApplyAPIView,
    CouponRemoveAPIView,
    CouponCheckAPIView,
    UserWeeklyCouponStatusAPIView,
)

urlpatterns = [
    # Customer / Public coupon listing
    path("coupons/", CouponListAPIView.as_view(), name="api_coupon_list"),

    # Coupon operations (Apply, Remove, Stateless check)
    path("coupons/apply/", CouponApplyAPIView.as_view(), name="api_coupon_apply"),
    path("coupons/remove/", CouponRemoveAPIView.as_view(), name="api_coupon_remove"),
    path("coupons/check/", CouponCheckAPIView.as_view(), name="api_coupon_check"),

    # Weekly coupon quota status
    path("coupons/weekly-status/", UserWeeklyCouponStatusAPIView.as_view(), name="api_coupon_weekly_status"),

    # Single coupon detail (by code or slug)
    path("coupons/<str:identifier>/", CouponDetailAPIView.as_view(), name="api_coupon_detail"),
]
