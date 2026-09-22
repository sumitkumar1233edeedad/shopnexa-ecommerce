from django.db import models
from django.conf import settings
from django.utils.text import slugify
import uuid


class Payment(models.Model):

    PAYMENT_STATUS = [
        ("pending", "Pending"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("refunded", "Refunded"),
    ]

    PAYMENT_METHOD = [
        ("cod", "Cash on Delivery"),
        ("online", "Online Payment"),
        ("razorpay", "Razorpay"),
        ("upi", "UPI"),
        ("card", "Card"),
        ("netbanking", "Net Banking"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="payments"
    )

    order = models.OneToOneField(
        "order.Order",
        on_delete=models.CASCADE,
        related_name="payment"
    )

    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD
    )

    transaction_id = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True
    )

    # Gateway specific tracking (Razorpay / Stripe)
    gateway_order_id = models.CharField(
        max_length=255,
        null=True,
        blank=True
    )

    gateway_payment_id = models.CharField(
        max_length=255,
        null=True,
        blank=True
    )

    gateway_signature = models.TextField(
        null=True,
        blank=True
    )

    currency = models.CharField(
        max_length=10,
        default="INR"
    )

    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS,
        default="pending"
    )

    paid_at = models.DateTimeField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    # URL slug
    slug = models.SlugField(
        max_length=150,
        unique=True,
        blank=True
    )

    def save(self, *args, **kwargs):

        if not self.slug:

            base_slug = slugify(
                f"{self.order.order_number}-{self.payment_method}"
            )

            self.slug = base_slug

            # Prevent duplicate slug
            if Payment.objects.filter(
                slug=self.slug
            ).exclude(pk=self.pk).exists():

                self.slug = (
                    f"{base_slug}-{uuid.uuid4().hex[:6]}"
                )

        super().save(*args, **kwargs)

        if self.status in ["completed", "pending"] and hasattr(self, "order") and self.order:
            if getattr(self.order, "coupon", None):
                try:
                    from apps.coupons.services import record_coupon_usage
                    record_coupon_usage(self.order)
                except Exception:
                    pass

    def __str__(self):
        return f"{self.order} - {self.amount} - {self.status}"