from django.db import models
from django.utils.text import slugify
from django.conf import settings
import uuid


class DateTime(models.Model):
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# =========================================================
# CATEGORY
# =========================================================

class Category(models.Model):
    name = models.CharField(
        max_length=100
    )

    slug = models.SlugField(
        max_length=120,
        unique=True,
        blank=True
    )

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):

        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1

            while Category.objects.filter(
                slug=slug
            ).exclude(pk=self.pk).exists():

                slug = f"{base_slug}-{counter}"
                counter += 1

            self.slug = slug

        super().save(*args, **kwargs)


# =========================================================
# COLOR
# =========================================================

class Color(models.Model):
    name = models.CharField(
        max_length=50
    )

    hex_code = models.CharField(
        max_length=7,
        blank=True
    )

    slug = models.SlugField(
        max_length=80,
        unique=True,
        blank=True
    )

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):

        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1

            while Color.objects.filter(
                slug=slug
            ).exclude(pk=self.pk).exists():

                slug = f"{base_slug}-{counter}"
                counter += 1

            self.slug = slug

        super().save(*args, **kwargs)


# =========================================================
# PRODUCT
# =========================================================

class Product(models.Model):

    cat = models.ManyToManyField(
        Category,
        related_name="product",
        blank=True
    )

    name = models.CharField(
        max_length=200
    )

    slug = models.SlugField(
        max_length=220,
        unique=True,
        blank=True
    )

    image = models.ImageField(
        upload_to="product/",
        blank=True,
        null=True
    )

    description = models.TextField(
        blank=True,
        default=""
    )

    brand = models.CharField(
        max_length=100
    )

    is_active = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        null=True
    )

    class Meta:
        indexes = [
            models.Index(fields=["is_active", "-id"]),
            models.Index(fields=["is_active", "brand"]),
            models.Index(fields=["is_active", "-created_at"]),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):

        if not self.slug:

            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1

            while Product.objects.filter(
                slug=slug
            ).exclude(pk=self.pk).exists():

                slug = f"{base_slug}-{counter}"
                counter += 1

            self.slug = slug

        super().save(*args, **kwargs)

    @property
    def default_variant(self):
        if hasattr(self, '_default_variant'):
            return self._default_variant
        if hasattr(self, '_prefetched_objects_cache') and 'variants' in self._prefetched_objects_cache:
            for variant in self.variants.all():
                if variant.is_active:
                    return variant
            return None
        return self.variants.filter(
            is_active=True
        ).first()

    @property
    def first_category(self):
        if hasattr(self, '_first_category'):
            return self._first_category
        if hasattr(self, '_prefetched_objects_cache') and 'cat' in self._prefetched_objects_cache:
            cats = self.cat.all()
            return cats[0] if cats else None
        return self.cat.first()

    @property
    def price(self):
        if hasattr(self, '_price') and self._price is not None:
            return self._price
        variant = self.default_variant
        return variant.price if variant else None

    @price.setter
    def price(self, value):
        self._price = value

    @property
    def min_price(self):
        if hasattr(self, '_min_price') and self._min_price is not None:
            return self._min_price
        if hasattr(self, '_prefetched_objects_cache') and 'variants' in self._prefetched_objects_cache:
            prices = [v.price for v in self.variants.all() if v.is_active and v.price is not None]
            return min(prices) if prices else None
        prices = self.variants.filter(
            is_active=True
        ).values_list(
            "price",
            flat=True
        )
        return min(prices) if prices else None

    @min_price.setter
    def min_price(self, value):
        self._min_price = value

    @property
    def max_price(self):
        if hasattr(self, '_max_price') and self._max_price is not None:
            return self._max_price
        if hasattr(self, '_prefetched_objects_cache') and 'variants' in self._prefetched_objects_cache:
            prices = [v.price for v in self.variants.all() if v.is_active and v.price is not None]
            return max(prices) if prices else None
        prices = self.variants.filter(
            is_active=True
        ).values_list(
            "price",
            flat=True
        )
        return max(prices) if prices else None

    @max_price.setter
    def max_price(self, value):
        self._max_price = value

    @property
    def in_stock(self):
        if hasattr(self, '_in_stock') and self._in_stock is not None:
            return self._in_stock
        if hasattr(self, '_prefetched_objects_cache') and 'variants' in self._prefetched_objects_cache:
            active_variants = [v for v in self.variants.all() if v.is_active]
            for variant in active_variants:
                if hasattr(variant, "stock") and variant.stock:
                    if variant.stock.available_quantity > 0:
                        return True
            return len(active_variants) > 0

        variants = self.variants.filter(
            is_active=True
        )

        for variant in variants:
            if hasattr(variant, "stock") and variant.stock:
                if variant.stock.available_quantity > 0:
                    return True

        return variants.exists()

    @property
    def average_rating(self):
        if hasattr(self, '_avg_rating') and self._avg_rating is not None:
            return round(float(self._avg_rating), 1)
        if hasattr(self, '_average_rating') and self._average_rating is not None:
            return round(float(self._average_rating), 1)
        if hasattr(self, '_prefetched_objects_cache') and 'reviews' in self._prefetched_objects_cache:
            reviews = self.reviews.all()
            if not reviews:
                return 5.0
            return round(
                sum(r.rating for r in reviews) / len(reviews),
                1
            )

        reviews = self.reviews.all()

        if not reviews.exists():
            return 5.0

        return round(
            sum(r.rating for r in reviews) / reviews.count(),
            1
        )

    @property
    def review_count(self):
        if hasattr(self, '_review_count') and self._review_count is not None:
            return self._review_count
        if hasattr(self, '_prefetched_objects_cache') and 'reviews' in self._prefetched_objects_cache:
            return len(self.reviews.all())
        return self.reviews.count()


# =========================================================
# PRODUCT VARIANT
# =========================================================

class ProductVariant(models.Model):

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="variants"
    )

    color = models.ForeignKey(
        Color,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="variants"
    )

    size = models.CharField(
        max_length=50,
        null=True,
        blank=True
    )

    sku = models.CharField(
        max_length=100,
        unique=True
    )

    slug = models.SlugField(
        max_length=250,
        unique=True,
        blank=True
    )

    is_active = models.BooleanField(
        default=True
    )

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    def __str__(self):
        return f"{self.product.name} - {self.sku}"

    def save(self, *args, **kwargs):

        if not self.slug:

            parts = [
                self.product.name
            ]

            if self.color:
                parts.append(self.color.name)

            if self.size:
                parts.append(self.size)

            parts.append(self.sku)

            base_slug = slugify("-".join(parts))
            slug = base_slug
            counter = 1

            while ProductVariant.objects.filter(
                slug=slug
            ).exclude(pk=self.pk).exists():

                slug = f"{base_slug}-{counter}"
                counter += 1

            self.slug = slug

        super().save(*args, **kwargs)

    @property
    def name(self):

        parts = [self.product.name]
        attrs = []

        if self.color:
            attrs.append(self.color.name)

        if self.size:
            attrs.append(self.size)

        if attrs:
            parts.append(
                f"({' / '.join(attrs)})"
            )

        return " ".join(parts)

    @property
    def image(self):
        return self.product.image

    @property
    def is_in_stock(self):

        if hasattr(self, "stock"):
            return self.stock.available_quantity > 0

        return True

    class Meta:
        indexes = [
            models.Index(fields=["product", "is_active"]),
            models.Index(fields=["is_active", "price"]),
        ]


# =========================================================
# STOCK
# =========================================================

class Stock(models.Model):

    variant = models.OneToOneField(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name="stock"
    )

    quantity = models.PositiveIntegerField(
        default=0
    )

    reserved_quantity = models.PositiveIntegerField(
        default=0
    )

    slug = models.SlugField(
        max_length=250,
        unique=True,
        blank=True
    )

    def save(self, *args, **kwargs):

        if not self.slug:

            base_slug = slugify(
                f"stock-{self.variant.slug}"
            )

            slug = base_slug
            counter = 1

            while Stock.objects.filter(
                slug=slug
            ).exclude(pk=self.pk).exists():

                slug = f"{base_slug}-{counter}"
                counter += 1

            self.slug = slug

        super().save(*args, **kwargs)

    @property
    def available_quantity(self):
        return max(
            0,
            self.quantity - self.reserved_quantity
        )

    def __str__(self):
        return (
            f"{self.variant.sku} - "
            f"{self.available_quantity}"
        )


# =========================================================
# REVIEW
# =========================================================

class Review(models.Model):

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reviews"
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="reviews",
        null=True
    )

    rating = models.PositiveSmallIntegerField(
        choices=[
            (1, "1 Star"),
            (2, "2 Stars"),
            (3, "3 Stars"),
            (4, "4 Stars"),
            (5, "5 Stars"),
        ],
        default=5
    )

    image = models.ImageField(
        upload_to="review_img",
        blank=True,
        null=True
    )

    product_review = models.TextField(
        blank=True,
        default=""
    )

    slug = models.SlugField(
        max_length=250,
        unique=True,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        null=True
    )

    def save(self, *args, **kwargs):

        if not self.slug:

            product_name = (
                self.product.name
                if self.product
                else "product"
            )

            base_slug = slugify(
                f"{self.user.username}-{product_name}"
            )

            # UUID makes every review URL unique
            self.slug = (
                f"{base_slug}-{uuid.uuid4().hex[:8]}"
            )

        super().save(*args, **kwargs)

    def __str__(self):

        prod_name = (
            self.product.name
            if self.product
            else "Unknown"
        )

        return (
            f"{self.user.username} - "
            f"{prod_name} ({self.rating}★)"
        )

    @property
    def comment(self):
        return self.product_review

    class Meta:
        indexes = [
            models.Index(fields=["product", "rating"]),
            models.Index(fields=["product", "user"]),
        ]


# =========================================================
# PRODUCT GALLERY IMAGE
# =========================================================

class ProductImage(models.Model):

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="images"
    )

    image = models.ImageField(
        upload_to="product/gallery/"
    )

    alt_text = models.CharField(
        max_length=150,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.product.name} Gallery Image ({self.pk})"