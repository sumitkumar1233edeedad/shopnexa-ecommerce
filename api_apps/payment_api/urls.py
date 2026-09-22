from django.urls import path
from .views import (
    PaymentProcessAPIView,
    PaymentVerifyAPIView,
    PaymentWebhookAPIView,
    PaymentListAPIView,
    PaymentDetailAPIView,
)

urlpatterns = [
    # List user's payment history
    path("payments/", PaymentListAPIView.as_view(), name="api_payment_list"),
    path("payment/", PaymentListAPIView.as_view(), name="api_payment_list_alias"),

    # Initialize / retrieve Razorpay payment parameters for an order
    path("payments/process/<slug:order_slug>/", PaymentProcessAPIView.as_view(), name="api_payment_process"),
    path("payment/process/<slug:order_slug>/", PaymentProcessAPIView.as_view(), name="api_payment_process_alias"),

    # Verify signature from checkout callback and complete order
    path("payments/verify/", PaymentVerifyAPIView.as_view(), name="api_payment_verify"),
    path("payment/verify/", PaymentVerifyAPIView.as_view(), name="api_payment_verify_alias"),

    # Razorpay asynchronous webhook endpoint
    path("payments/webhook/", PaymentWebhookAPIView.as_view(), name="api_payment_webhook"),
    path("payment/webhook/", PaymentWebhookAPIView.as_view(), name="api_payment_webhook_alias"),

    # Payment detail by slug, transaction_id, or order_number
    path("payments/<str:identifier>/", PaymentDetailAPIView.as_view(), name="api_payment_detail"),
    path("payment/<str:identifier>/", PaymentDetailAPIView.as_view(), name="api_payment_detail_alias"),
]
