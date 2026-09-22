from django.urls import path
from .views import *

urlpatterns = [
    path('login/', LoginAPIView.as_view(), name='api_login'),
    path('logout/', LogoutAPIView.as_view(), name='api_logout'),
    path('register/', RegisterAPIView.as_view(), name='api_register'),
    path('verify-otp/', VerifyOTPAPIView.as_view(), name="verify_otp"),
    path("forgot-password/", ForgotPasswordAPIView.as_view(), name="forgot_password"),
    path("verify-reset-otp/", VerifyResetOTPAPIView.as_view(), name="verify_reset_otp"),
    path("resend-reset-otp/", ResendResetOTPAPIView.as_view(), name="resend_reset_otp"),
    path("reset-password/", ResetPasswordAPIView.as_view(), name="reset_password"),
    path("profile/", ProfileAPIView.as_view(), name="api_profile"),
    path("profile/<slug:slug>/", ProfileAPIView.as_view(), name="api_profile_slug"),

    # Wishlist APIs (Unified WishListAPIView)
    path("wishlist/", WishListAPIView.as_view(), name="api_wishlist"),
    path("wishlist/toggle/", WishListAPIView.as_view(), name="api_toggle_wishlist_body"),
    path("wishlist/toggle/<slug:slug>/", WishListAPIView.as_view(), name="api_toggle_wishlist"),
    path("wishlist/remove/", WishListAPIView.as_view(), name="api_remove_from_wishlist_body"),
    path("wishlist/remove/<slug:slug>/", WishListAPIView.as_view(), name="api_remove_from_wishlist"),
    path("wishlist/<slug:slug>/", WishListAPIView.as_view(), name="api_wishlist_item"),

    # Address APIs (Unified AddressAPIView)
    path("address/", AddressAPIView.as_view(), name="api_address"),
    path("address/add/", AddressAPIView.as_view(), name="api_address_add"),
    path("address/<slug:slug>/set-default/", AddressAPIView.as_view(), name="api_address_set_default"),
    path("address/<slug:slug>/delete/", AddressAPIView.as_view(), name="api_address_delete"),
    path("address/delete/<slug:slug>/", AddressAPIView.as_view(), name="api_address_delete_alt"),
    path("address/<slug:slug>/", AddressAPIView.as_view(), name="api_address_detail"),
]


