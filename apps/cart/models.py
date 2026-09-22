from django.db import models
from django.conf import settings
from django.utils.text import slugify
import uuid


class Cart(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cart"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    slug = models.SlugField(
        max_length=255,
        unique=True,
        blank=True
    )

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(f"{self.user.username}-cart")

            self.slug = base_slug

            if Cart.objects.filter(
                slug=self.slug
            ).exclude(pk=self.pk).exists():

                self.slug = (
                    f"{base_slug}-{uuid.uuid4().hex[:6]}"
                )

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username}'s Cart"

    @property
    def total_price(self):
        return sum(
            item.total_price
            for item in self.items.all()
        )

    @property
    def total_items(self):
        return sum(
            item.quantity
            for item in self.items.all()
        )


class CartItem(models.Model):
    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name="items"
    )

    product = models.ForeignKey(
        "products.ProductVariant",
        on_delete=models.CASCADE
    )

    quantity = models.PositiveIntegerField(
        default=1
    )

    slug = models.SlugField(
        max_length=255,
        unique=True,
        blank=True
    )

    def save(self, *args, **kwargs):
        if not self.slug:

            product_slug = (
                self.product.slug
                if self.product.slug
                else slugify(self.product.product.name)
            )

            base_slug = slugify(
                f"{self.cart.user.username}-{product_slug}"
            )

            self.slug = base_slug

            # Prevent duplicate slug
            if CartItem.objects.filter(
                slug=self.slug
            ).exclude(pk=self.pk).exists():

                self.slug = (
                    f"{base_slug}-{uuid.uuid4().hex[:6]}"
                )

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product} x {self.quantity}"

    @property
    def variant(self):
        return self.product

    @property
    def product_item(self):
        return self.product.product

    @property
    def total_price(self):
        return self.product.price * self.quantity