from django.urls import path
from .views import payment_process, payment_verify, payment_webhook

app_name = "payment"

urlpatterns = [
    path("process/<slug:order_slug>/", payment_process, name="process"),
    path("verify/", payment_verify, name="verify"),
    path("webhook/", payment_webhook, name="webhook"),
]
