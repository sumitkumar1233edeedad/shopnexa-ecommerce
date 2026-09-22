from django.db import models
from django.conf import settings
from django.utils.text import slugify
from decimal import Decimal
import uuid


class Order(models.Model):

    STATUS_CHOICES = [
        ("pending_payment", "Payment Pending"),
        ("pending", "Pending"),
        ("confirmed", "Confirmed"),
        ("processing", "Processing"),
        ("shipped", "Shipped"),
        ("delivered", "Delivered"),
        ("cancelled", "Cancelled"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="orders"
    )

    order_number = models.CharField(
        max_length=30,
        unique=True
    )

    slug = models.SlugField(
        max_length=100,
        unique=True,
        blank=True
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending"
    )

    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    coupon = models.ForeignKey(
        "coupons.Coupon",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders"
    )

    discount_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00
    )

    shipping_name = models.CharField(
        max_length=100,
        blank=True,
        default=""
    )

    shipping_phone = models.CharField(
        max_length=20,
        blank=True,
        default=""
    )

    shipping_city = models.CharField(
        max_length=100,
        blank=True,
        default=""
    )

    shipping_pincode = models.CharField(
        max_length=10,
        blank=True,
        default=""
    )

    shipping_address = models.TextField()

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def save(self, *args, **kwargs):

        if not self.slug:

            base_slug = slugify(
                f"order-{self.order_number}"
            )

            self.slug = base_slug

            # Prevent duplicate slug
            if Order.objects.filter(
                slug=self.slug
            ).exclude(pk=self.pk).exists():

                self.slug = (
                    f"{base_slug}-{uuid.uuid4().hex[:6]}"
                )

        super().save(*args, **kwargs)

    def __str__(self):
        return self.order_number

    @property
    def total_items(self):
        return sum(
            item.quantity
            for item in self.items.all()
        )

    @property
    def items_subtotal(self):
        return sum(
            item.subtotal
            for item in self.items.all()
        )

    @property
    def calculated_total(self):
        subtotal = self.items_subtotal
        discount = self.discount_amount or Decimal("0.00")
        shipping = Decimal("0.00") if subtotal >= 500 else Decimal("50.00")
        return max(Decimal("0.00"), subtotal - discount) + shipping

    @property
    def total(self):
        if self.total_amount is not None:
            return self.total_amount
        return self.calculated_total


class OrderItem(models.Model):

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items"
    )

    variant = models.ForeignKey(
        "products.ProductVariant",
        on_delete=models.PROTECT,
        related_name="order_items"
    )

    quantity = models.PositiveIntegerField()

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    slug = models.SlugField(
        max_length=150,
        unique=True,
        blank=True
    )

    def save(self, *args, **kwargs):

        if not self.slug:

            product_name = (
                self.variant.product.name
                if self.variant.product
                else self.variant.sku
            )

            base_slug = slugify(
                f"{self.order.order_number}-{product_name}-{self.variant.sku}"
            )

            self.slug = base_slug

            # Prevent duplicate slug
            if OrderItem.objects.filter(
                slug=self.slug
            ).exclude(pk=self.pk).exists():

                self.slug = (
                    f"{base_slug}-{uuid.uuid4().hex[:6]}"
                )

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.order.order_number} - {self.variant.sku}"

    @property
    def subtotal(self):
        return self.price * self.quantity