import uuid
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.text import slugify


class Coupon(models.Model):
    DISCOUNT_TYPE_CHOICES = [
        ("percentage", "Percentage (%)"),
        ("fixed", "Fixed Amount (₹)"),
    ]

    code = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        help_text="Unique coupon code (case-insensitive in validation)."
    )
    description = models.TextField(
        blank=True,
        default="",
        help_text="Optional description or promotion terms."
    )
    discount_type = models.CharField(
        max_length=20,
        choices=DISCOUNT_TYPE_CHOICES,
        default="percentage"
    )
    discount_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Percentage value (e.g. 20 for 20%) or fixed amount in ₹."
    )
    minimum_order_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Minimum cart subtotal required to use this coupon."
    )
    maximum_discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum discount cap (useful for percentage discounts)."
    )
    valid_from = models.DateTimeField(
        default=timezone.now,
        help_text="Start of validity period."
    )
    valid_until = models.DateTimeField(
        help_text="End of validity period."
    )
    usage_limit = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Total maximum allowed successful uses across all users. Leave blank for unlimited."
    )
    used_count = models.PositiveIntegerField(
        default=0,
        help_text="Actual count of successful orders placed with this coupon."
    )
    per_user_limit = models.PositiveIntegerField(
        default=1,
        null=True,
        blank=True,
        help_text="Maximum allowed successful uses per individual user. Leave blank for unlimited."
    )
    weekly_user_limit = models.PositiveIntegerField(
        default=5,
        help_text="Maximum allowed successful uses per individual user per week."
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Master toggle to activate or deactivate this coupon."
    )
    slug = models.SlugField(
        max_length=100,
        unique=True,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Coupon"
        verbose_name_plural = "Coupons"

    def __str__(self):
        return self.code.upper()

    def clean(self):
        if self.code:
            self.code = self.code.strip().upper()
        if self.valid_from and self.valid_until and self.valid_until <= self.valid_from:
            raise ValidationError({
                "valid_until": "End date/time must be after start date/time."
            })
        if self.discount_value is not None and self.discount_value <= 0:
            raise ValidationError({
                "discount_value": "Discount value must be greater than zero."
            })
        if self.discount_type == "percentage" and self.discount_value and self.discount_value > 100:
            raise ValidationError({
                "discount_value": "Percentage discount cannot exceed 100%."
            })

    def save(self, *args, **kwargs):
        if self.code:
            self.code = self.code.strip().upper()
        if not self.slug:
            base_slug = slugify(self.code)
            self.slug = base_slug
            if Coupon.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                self.slug = f"{base_slug}-{uuid.uuid4().hex[:6]}"
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        return timezone.now() > self.valid_until

    @property
    def is_upcoming(self):
        return timezone.now() < self.valid_from

    @property
    def status_display(self):
        now = timezone.now()
        if not self.is_active:
            return "Inactive"
        if now > self.valid_until:
            return "Expired"
        if now < self.valid_from:
            return "Upcoming"
        if self.usage_limit is not None and self.used_count >= self.usage_limit:
            return "Limit Reached"
        return "Active"

    def is_valid_now(self, dt=None):
        now = dt or timezone.now()
        if not self.is_active:
            return False, "This coupon is not active."
        if now < self.valid_from:
            return False, f"This coupon is not active yet. It starts on {self.valid_from.strftime('%d %b %Y')}."
        if now > self.valid_until:
            return False, "This coupon has expired."
        if self.usage_limit is not None and self.used_count >= self.usage_limit:
            return False, "This coupon has reached its usage limit."
        return True, ""

    def calculate_discount(self, order_amount):
        """
        Calculates discount for the given order_amount (subtotal).
        Ensures discount does not exceed order_amount or maximum_discount_amount.
        """
        order_amount = Decimal(str(order_amount))
        if order_amount <= 0:
            return Decimal("0.00")

        if self.discount_type == "percentage":
            discount = (order_amount * self.discount_value) / Decimal("100.00")
            if self.maximum_discount_amount is not None:
                discount = min(discount, self.maximum_discount_amount)
        else:
            discount = self.discount_value

        # Cap at order_amount so total cannot be negative
        discount = min(discount, order_amount)
        return max(Decimal("0.00"), discount.quantize(Decimal("0.01")))


class CouponConfiguration(models.Model):
    """
    Singleton configuration model allowing admin to configure global coupon settings,
    such as the weekly user coupon limit (default 5).
    """
    weekly_user_limit = models.PositiveIntegerField(
        default=5,
        verbose_name="Weekly user coupon limit",
        help_text="Maximum successful coupon uses allowed per registered user per week (Mon 00:00 to Sun 23:59:59)."
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Coupon Configuration"
        verbose_name_plural = "Coupon Configuration"

    def __str__(self):
        return f"Global Coupon Configuration (Weekly Limit: {self.weekly_user_limit})"

    def save(self, *args, **kwargs):
        # Enforce singleton in database
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_config(cls):
        config, _ = cls.objects.get_or_create(pk=1, defaults={"weekly_user_limit": 5})
        return config

    @classmethod
    def get_weekly_limit(cls):
        return cls.get_config().weekly_user_limit


class CouponUsage(models.Model):
    """
    Tracks successful coupon usage attached to a successfully completed order/payment.
    """
    coupon = models.ForeignKey(
        Coupon,
        on_delete=models.PROTECT,
        related_name="usages"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="coupon_usages"
    )
    order = models.OneToOneField(
        "order.Order",
        on_delete=models.CASCADE,
        related_name="coupon_usage",
        help_text="The completed order this coupon usage belongs to. Unique to prevent duplicate records."
    )
    discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Discount amount granted on this order."
    )
    used_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        help_text="Time of successful coupon usage, used for weekly limit calculations."
    )
    slug = models.SlugField(
        max_length=150,
        unique=True,
        blank=True
    )

    class Meta:
        ordering = ["-used_at"]
        verbose_name = "Coupon Usage"
        verbose_name_plural = "Coupon Usages"
        indexes = [
            models.Index(fields=["user", "used_at"], name="idx_user_used_at"),
            models.Index(fields=["coupon", "user"], name="idx_coupon_user"),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            order_num = getattr(self.order, "order_number", "order") if self.order else "order"
            base_slug = slugify(f"usage-{self.coupon.code}-{self.user.username}-{order_num}")
            self.slug = base_slug
            if CouponUsage.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                self.slug = f"{base_slug}-{uuid.uuid4().hex[:6]}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} - {self.coupon.code} (Order: {self.order.order_number}) on {self.used_at:%Y-%m-%d %H:%M}"
