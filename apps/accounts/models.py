from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.utils.text import slugify
from django.utils import timezone
from datetime import timedelta
import uuid


# =========================================================
# CUSTOM USER
# =========================================================

class CustomUser(AbstractUser):
    # Enforce email uniqueness
    email = models.EmailField(
        unique=True,
        error_messages={
            'unique': "An account with this email already exists.",
        }
    )

    # Verification & OTP fields directly on user model
    is_email_verified = models.BooleanField(default=False)
    temp_otp = models.CharField(max_length=6, blank=True, null=True)
    is_activated = models.BooleanField(default=False)
    otp_created_at = models.DateTimeField(null=True, blank=True)

    # Optional: ensure case-insensitive clean
    def clean(self):
        super().clean()
        if self.email:
            self.email = self.email.strip().lower()

    def __str__(self):
        return self.username

    @property
    def slug(self):
        try:
            if hasattr(self, 'profile') and self.profile and self.profile.slug:
                return self.profile.slug
        except Exception:
            pass
        return self.username


class DateTime(models.Model):
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True



# =========================================================
# PROFILE
# =========================================================


class Profile(models.Model):
    name = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile"
    )

    phone = models.CharField(
        max_length=15,
        null=True,
        blank=True
    )

    profile_picture = models.ImageField(
        upload_to="profile_pic",
        default="default/x.jpg",
        null=True,
        blank=True
    )

    slug = models.SlugField(
        unique=True,
        blank=True
    )

    def __str__(self):
        return self.name.username

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name.username)
            self.slug = base_slug

            # Prevent duplicate slug
            if Profile.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                self.slug = f"{base_slug}-{uuid.uuid4().hex[:6]}"

        super().save(*args, **kwargs)


# =========================================================
# ADDRESS
# =========================================================


class Address(models.Model):

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="addresses",
        null=True,
        blank=True
    )

    name = models.CharField(
        max_length=100
    )

    phone = models.CharField(
        max_length=15,
        null=True,
        blank=True
    )

    pincode = models.CharField(
        max_length=10
    )

    locality = models.CharField(
        max_length=200,
        null=True,
        blank=True
    )

    address_line = models.CharField(
        max_length=255,
        default=""
    )

    city = models.CharField(
        max_length=100
    )

    STATE_CHOICES = [
        ("AP", "Andhra Pradesh"),
        ("AR", "Arunachal Pradesh"),
        ("AS", "Assam"),
        ("BR", "Bihar"),
        ("CG", "Chhattisgarh"),
        ("GA", "Goa"),
        ("GJ", "Gujarat"),
        ("HR", "Haryana"),
        ("HP", "Himachal Pradesh"),
        ("JH", "Jharkhand"),
        ("KA", "Karnataka"),
        ("KL", "Kerala"),
        ("MP", "Madhya Pradesh"),
        ("MH", "Maharashtra"),
        ("MN", "Manipur"),
        ("ML", "Meghalaya"),
        ("MZ", "Mizoram"),
        ("NL", "Nagaland"),
        ("OD", "Odisha"),
        ("PB", "Punjab"),
        ("RJ", "Rajasthan"),
        ("SK", "Sikkim"),
        ("TN", "Tamil Nadu"),
        ("TS", "Telangana"),
        ("TR", "Tripura"),
        ("UP", "Uttar Pradesh"),
        ("UK", "Uttarakhand"),
        ("WB", "West Bengal"),
        ("AN", "Andaman and Nicobar Islands"),
        ("CH", "Chandigarh"),
        ("DN", "Dadra and Nagar Haveli and Daman and Diu"),
        ("DL", "Delhi"),
        ("JK", "Jammu and Kashmir"),
        ("LA", "Ladakh"),
        ("LD", "Lakshadweep"),
        ("PY", "Puducherry"),
    ]

    state = models.CharField(
        max_length=50,
        choices=STATE_CHOICES
    )

    landmark = models.CharField(
        max_length=200,
        null=True,
        blank=True
    )

    ADDRESS_TYPE_CHOICES = [
        ("HOME", "Home"),
        ("WORK", "Work"),
    ]

    address_type = models.CharField(
        max_length=10,
        choices=ADDRESS_TYPE_CHOICES,
        default="HOME"
    )

    is_default = models.BooleanField(
        default=False
    )

    # ==========================
    # GPS / LOCATION TRACKER
    # ==========================

    latitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
        help_text="GPS latitude from browser geolocation"
    )

    longitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
        help_text="GPS longitude from browser geolocation"
    )

    area = models.CharField(
        max_length=200,
        null=True,
        blank=True,
        help_text="Neighbourhood / area detected from GPS"
    )

    formatted_address = models.TextField(
        null=True,
        blank=True,
        help_text="Full formatted address from reverse geocoding"
    )

    # ==========================
    # SLUG
    # ==========================

    slug = models.SlugField(
        unique=True,
        blank=True
    )

    def save(self, *args, **kwargs):

        if not self.slug:

            base_slug = slugify(
                f"{self.name}-{self.city}-{self.pincode}"
            )

            self.slug = base_slug

            # Prevent duplicate slug
            if Address.objects.filter(
                slug=self.slug
            ).exclude(pk=self.pk).exists():

                self.slug = (
                    f"{base_slug}-{uuid.uuid4().hex[:6]}"
                )

        super().save(*args, **kwargs)

    @property
    def full_name(self):
        return self.name

    @property
    def locataliyt(self):
        return self.locality

    @property
    def Address(self):
        return self.address_line

    def __str__(self):
        return f"{self.name} - {self.city}, {self.pincode}"


# =========================================================
# WISHLIST
# =========================================================

class WishList(models.Model):

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wishlist",
        null=True,
        blank=True
    )

    product = models.ForeignKey(
        "products.Product",
        on_delete=models.CASCADE,
        related_name="wishlisted_by"
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        null=True
    )

    # ==========================
    # SLUG
    # ==========================

    slug = models.SlugField(
        unique=True,
        blank=True
    )

    class Meta:
        unique_together = ("user", "product")

    def save(self, *args, **kwargs):

        if not self.slug:

            username = (
                self.user.username
                if self.user
                else "anonymous"
            )

            product_slug = (
                self.product.slug
                if self.product.slug
                else slugify(self.product.name)
            )

            base_slug = slugify(
                f"{username}-{product_slug}"
            )

            self.slug = base_slug

            # Prevent duplicate slug
            if WishList.objects.filter(
                slug=self.slug
            ).exclude(pk=self.pk).exists():

                self.slug = (
                    f"{base_slug}-{uuid.uuid4().hex[:6]}"
                )

        super().save(*args, **kwargs)

    def __str__(self):

        username = (
            self.user.username
            if self.user
            else "Anonymous"
        )

        return f"{username} - {self.product.name}"