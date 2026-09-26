from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import get_user_model, authenticate, login, logout, update_session_auth_hash
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta
from django.db import transaction
from .models import *
from .tasks import validate_user_email, generate_and_send_otp, send_registration_email
import re
import logging
from apps.products.validators import validate_uploaded_image

logger = logging.getLogger(__name__)

User = get_user_model()
from apps.products.models import *
from apps.cart.models import *
from apps.order.models import Order
from apps.cart.views import *
from apps.cart.utils import get_cart_count
from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Prefetch, Avg, Count, Min, Q, Value
 
from django.db.models.functions import Coalesce
from django.core.cache import cache

# =========================================================
# PASSWORD RESET VIEWS (FORGOT PASSWORD & CHANGE PASSWORD)
# =========================================================

def forgot_password_view(request):
    default_email = request.user.email if request.user.is_authenticated else ""

    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()

        is_valid_email, email_error = validate_user_email(email)
        if not is_valid_email:
            messages.error(request, email_error)
            return render(request, "accounts/forgot_password.html", {"default_email": default_email})

        user = User.objects.filter(email=email, is_active=True).first()

        if not user:
            messages.error(request, "No active account found with this email address.")
            return render(request, "accounts/forgot_password.html", {"default_email": default_email})

        try:
            generate_and_send_otp(user, purpose="password_reset")
            request.session["reset_user_id"] = user.id
            request.session["reset_otp_verified"] = False
            messages.success(request, f"A 6-digit password reset code has been sent to {email}.")
            return redirect("verify_reset_otp")
        except Exception as e:
            messages.error(request, f"Failed to send reset email: {e}")
            return render(request, "accounts/forgot_password.html", {"default_email": default_email})

    return render(request, "accounts/forgot_password.html", {"default_email": default_email})


def verify_reset_otp_view(request):
    user_id = request.session.get("reset_user_id")
    if not user_id:
        messages.error(request, "Session expired. Please enter your email again.")
        return redirect("forgot_password")

    user = get_object_or_404(User, id=user_id)

    if request.method == "POST":
        entered_otp = request.POST.get("otp", "").strip()

        if not entered_otp:
            messages.error(request, "Please enter the 6-digit reset code.")
            return render(request, "accounts/verify_reset_otp.html", {"email": user.email})

        if not user.temp_otp or user.temp_otp != entered_otp:
            messages.error(request, "Invalid reset code. Please check your email and try again.")
            return render(request, "accounts/verify_reset_otp.html", {"email": user.email})

        if user.otp_created_at and timezone.now() > user.otp_created_at + timedelta(minutes=10):
            messages.error(request, "This reset code has expired (valid for 10 minutes only). Please request a new one.")
            return render(request, "accounts/verify_reset_otp.html", {"email": user.email})

        # Clear OTP once used
        user.temp_otp = None
        user.otp_created_at = None
        user.save(update_fields=["temp_otp", "otp_created_at"])

        request.session["reset_otp_verified"] = True
        messages.success(request, "OTP verified! Please set your new password.")
        return redirect("reset_password")

    return render(request, "accounts/verify_reset_otp.html", {"email": user.email})


def resend_reset_otp_view(request):
    user_id = request.session.get("reset_user_id")
    if not user_id:
        messages.error(request, "Session expired. Please start over.")
        return redirect("forgot_password")

    user = get_object_or_404(User, id=user_id)
    try:
        generate_and_send_otp(user, purpose="password_reset")
        messages.success(request, f"A new reset code has been sent to {user.email}.")
    except Exception as e:
        messages.error(request, f"Failed to resend code: {e}")

    return redirect("verify_reset_otp")


def reset_password_view(request):
    user_id = request.session.get("reset_user_id")
    is_verified = request.session.get("reset_otp_verified", False)

    if not user_id or not is_verified:
        messages.error(request, "Unauthorized access or session expired. Please verify your OTP first.")
        return redirect("forgot_password")

    user = get_object_or_404(User, id=user_id)

    if request.method == "POST":
        new_password = request.POST.get("new_password")
        confirm_password = request.POST.get("confirm_password")

        if new_password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return render(request, "accounts/reset_password.html")

        if len(new_password) < 6:
            messages.error(request, "Password must be at least 6 characters long.")
            return render(request, "accounts/reset_password.html")

        user.set_password(new_password)
        user.is_email_verified = True
        user.is_activated = True
        user.is_active = True
        user.temp_otp = None
        user.otp_created_at = None
        user.save()

        if "reset_user_id" in request.session:
            del request.session["reset_user_id"]
        if "reset_otp_verified" in request.session:
            del request.session["reset_otp_verified"]

        if request.user.is_authenticated:
            update_session_auth_hash(request, user)
            messages.success(request, "🎉 Your password has been updated successfully!")
            return redirect("profile_default")
        else:
            messages.success(request, "Password changed successfully! You can now log in with your new password.")
            return redirect("login")

    return render(request, "accounts/reset_password.html")


@login_required(login_url='login')
def change_password_view(request):
    user = request.user

    if request.method == "POST":
        current_password = request.POST.get("current_password", "").strip()
        new_password = request.POST.get("new_password", "").strip()
        confirm_password = request.POST.get("confirm_password", "").strip()

        if not current_password or not new_password or not confirm_password:
            messages.error(request, "All password fields are required.")
            return render(request, "accounts/change_password.html")

        if not user.check_password(current_password):
            messages.error(request, "Current password is incorrect. Please try again or reset via Email OTP.")
            return render(request, "accounts/change_password.html")

        if new_password != confirm_password:
            messages.error(request, "New password and Confirm password do not match.")
            return render(request, "accounts/change_password.html")

        if len(new_password) < 6:
            messages.error(request, "New password must be at least 6 characters long.")
            return render(request, "accounts/change_password.html")

        if current_password == new_password:
            messages.error(request, "New password cannot be the same as your current password.")
            return render(request, "accounts/change_password.html")

        user.set_password(new_password)
        user.save()
        update_session_auth_hash(request, user)

        messages.success(request, "🎉 Your password has been changed successfully!")
        return redirect("profile_default")

    return render(request, "accounts/change_password.html")




def home(request):
    active_variants_prefetch = Prefetch(
        "variants",
        queryset=ProductVariant.objects.filter(is_active=True).select_related("color", "stock")
    )

    products = list(
        Product.objects
        .filter(is_active=True)
        .annotate(
            _avg_rating=Coalesce(Avg("reviews__rating"), Value(5.0)),
            _review_count=Count("reviews", distinct=True),
        )
        .prefetch_related("cat", active_variants_prefetch)
        .order_by("-id")[:20]
    )

    latest_products = products[:3]  # still pending your confirmation on id/created_at ordering

    categories = cache.get("home_categories_v1")
    if categories is None:
        categories = list(
            Category.objects.annotate(
                first_product_id=Min("product__id", filter=Q(product__is_active=True))
            )
        )
        first_ids = [c.first_product_id for c in categories if c.first_product_id]
        first_products = {
            p.id: p for p in Product.objects.filter(id__in=first_ids).only("id", "name", "image", "slug")
        }
        for c in categories:
            c.first_product = first_products.get(c.first_product_id)
        cache.set("home_categories_v1", categories, 300)

    wishlist_product_ids = set()
    if request.user.is_authenticated:
        wishlist_product_ids = set(
            WishList.objects.filter(user=request.user).values_list("product_id", flat=True)
        )

    cart_count = get_cart_count(request)

    return render(request, "home.html", {
        "products": products,
        "categories": categories,
        "wishlist_product_ids": wishlist_product_ids,
        "cart_count": cart_count,
        "latest_products": latest_products,
    })


def login_view(request):
    if request.user.is_authenticated:
        if request.user.is_staff or request.user.is_superuser:
            return redirect("admin_dashboard")
        return redirect("home")

    if request.method == "POST":
        username_or_email = request.POST.get("username", "").strip()
        password = request.POST.get("password")

        if not username_or_email or not password:
            messages.error(request, "Please enter both username/email and password.")
            return render(request, "accounts/login.html")

        # 1. Try finding user by username or email
        user_obj = User.objects.filter(username__iexact=username_or_email).first()
        if not user_obj:
            user_obj = User.objects.filter(email__iexact=username_or_email).first()

        # 2. If user exists, check password
        if user_obj and user_obj.check_password(password):
            # Check if email is NOT verified OR account is NOT activated
            if not user_obj.is_email_verified or not user_obj.is_activated:
                # Preserve intended destination in session
                next_url = request.GET.get("next") or request.POST.get("next")
                if next_url and not next_url.startswith("/login"):
                    request.session["next_url"] = next_url

                try:
                    generate_and_send_otp(user_obj, purpose="registration")
                    request.session["otp_user_id"] = user_obj.id
                    messages.warning(
                        request,
                        f"Your email is not verified yet. We've sent a 6-digit OTP code to {user_obj.email}."
                    )
                    return redirect("verify_otp")
                except Exception as e:
                    messages.error(request, f"Failed to send verification code: {e}")
                    return render(request, "accounts/login.html")

            # Authenticate and login active verified user
            user = authenticate(
                request,
                username=user_obj.username,
                password=password
            )

            if user is not None:
                login(request, user)


                merge_session_cart_to_user(request, user)
                messages.success(request, f"Welcome back, {user.first_name or user.username}!")

                next_url = request.GET.get("next") or request.POST.get("next")
                if next_url and next_url.strip() and not next_url.startswith("/login"):
                    return redirect(next_url)

                if user.is_staff or user.is_superuser:
                    return redirect("admin_dashboard")

                return redirect("home")

        messages.error(request, "Invalid username/email or password.")

    return render(
        request,
        "accounts/login.html"
    )


def register_view(request):
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        email = request.POST.get("email", "").strip().lower()
        password = request.POST.get("password")
        confirm_password = request.POST.get("confirm_password")

        # 1. Check required fields and passwords
        if not first_name:
            messages.error(request, "First name is required.")
            return redirect("register")

        if password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return redirect("register")

        if len(password) < 6:
            messages.error(request, "Password must be at least 6 characters long.")
            return redirect("register")

        # 2. Strict Email Validation
        is_valid_email, email_error = validate_user_email(email)
        if not is_valid_email:
            messages.error(request, email_error)
            return redirect("register")

        # 3. Check active user with same email
        if User.objects.filter(email__iexact=email, is_active=True).exists():
            messages.error(request, "An account with this email already exists. Please log in or reset your password.")
            return redirect("register")

        # 4. Generate unique username from first_name + last_name
        clean_first = re.sub(r'[^a-zA-Z0-9]', '', first_name).lower()
        clean_last = re.sub(r'[^a-zA-Z0-9]', '', last_name).lower()

        if clean_first and clean_last:
            base_username = f"{clean_first}_{clean_last}"
        elif clean_first:
            base_username = clean_first
        else:
            base_username = email.split("@")[0].lower()
            base_username = re.sub(r'[^a-zA-Z0-9]', '', base_username) or "user"

        username = base_username
        counter = 1
        while User.objects.filter(username__iexact=username, is_active=True).exists():
            username = f"{base_username}_{counter}"
            counter += 1

        # Clean up any unverified stale accounts with the same username or email
        User.objects.filter(username__iexact=username, is_active=False).delete()
        User.objects.filter(email__iexact=email, is_active=False).delete()

        # 5. Create inactive user awaiting OTP verification
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            is_active=False,
            is_email_verified=False,
            is_activated=False
        )

        # 6. Send OTP Email
        try:
            generate_and_send_otp(user, purpose="registration")
            request.session["otp_user_id"] = user.id
            messages.success(request, f"A 6-digit verification code has been sent to {email}. Valid for 10 minutes.")
            return redirect("verify_otp")
        except Exception as e:
            user.delete()
            messages.error(request, f"Failed to send verification email. Error: {e}")
            return redirect("register")

    return render(request, "accounts/register.html")



def verify_otp_view(request):
    user_id = request.session.get("otp_user_id")
    if not user_id:
        messages.error(request, "Session expired or invalid. Please register again.")
        return redirect("register")

    user = get_object_or_404(User, id=user_id)

    if request.method == "POST":
        entered_otp = request.POST.get("otp", "").strip()

        if not entered_otp:
            messages.error(request, "Please enter the 6-digit OTP code.")
            return render(request, "accounts/verify_otp.html", {"email": user.email})

        if not user.temp_otp or user.temp_otp != entered_otp:
            messages.error(request, "Invalid OTP code. Please check your email and try again.")
            return render(request, "accounts/verify_otp.html", {"email": user.email})

        if user.otp_created_at and timezone.now() > user.otp_created_at + timedelta(minutes=10):
            messages.error(request, "This OTP has expired (valid for 10 minutes only). Please click Resend OTP.")
            return render(request, "accounts/verify_otp.html", {"email": user.email})

        # Clear OTP and activate account
        user.temp_otp = None
        user.otp_created_at = None
        user.is_email_verified = True
        user.is_activated = True
        user.is_active = True
        user.save()

        # Send registration welcome email only after successful OTP verification
        transaction.on_commit(lambda: send_registration_email.delay(user.id))

        # Ensure profile exists
        Profile.objects.get_or_create(name=user)

        # Auto login
        login(request, user)
        merge_session_cart_to_user(request, user)

        if "otp_user_id" in request.session:
            del request.session["otp_user_id"]

        messages.success(request, "🎉 Email verified successfully! Welcome to AI Store.")

        # Check for preserved next_url in session
        next_url = request.session.pop("next_url", None)
        if next_url and next_url.strip() and not next_url.startswith("/login"):
            return redirect(next_url)

        # Redirect according to role/permissions
        if user.is_staff or user.is_superuser:
            return redirect("admin_dashboard")

        return redirect("home")

    return render(request, "accounts/verify_otp.html", {"email": user.email})


def resend_otp_view(request):
    user_id = request.session.get("otp_user_id")
    if not user_id:
        messages.error(request, "Session expired. Please register again.")
        return redirect("register")

    user = get_object_or_404(User, id=user_id)
    try:
        generate_and_send_otp(user, purpose="registration")
        messages.success(request, f"A fresh OTP code has been sent to {user.email}. Valid for 10 minutes.")
    except Exception as e:
        messages.error(request, f"Failed to resend OTP: {e}")

    return redirect("verify_otp")



@login_required(login_url='login')
def logout_view(request):
    logout(request)
    return redirect("login")


@login_required(login_url='login')
def profile_view(request, slug=None):

    user = request.user

    # Get or create profile
    profile, _ = Profile.objects.get_or_create(name=user)

    # If URL slug doesn't match current user's slug
    valid_identifiers = [profile.slug, user.username, str(user.id)]
    if slug and slug not in valid_identifiers and not request.user.is_staff:
        return redirect(
            "profile",
            slug=profile.slug
        )

    addresses = Address.objects.filter(
        user=user
    ).order_by("-is_default", "-id")

    wishlist_items = WishList.objects.filter(
        user=user
    ).select_related("product")[:4]

    cart_count = get_cart_count(request)
    orders_count = Order.objects.filter(user=user).count()
    wishlist_count = WishList.objects.filter(user=user).count()
    addresses_count = addresses.count()

    return render(
        request,
        "accounts/profile.html",
        {
            "user": user,
            "profile": profile,
            "addresses": addresses,
            "wishlist_items": wishlist_items,
            "cart_count": cart_count,
            "orders_count": orders_count,
            "wishlist_count": wishlist_count,
            "addresses_count": addresses_count,
        }
    )
@login_required(login_url='login')
def update_profile(request, slug=None):

    user = request.user

    profile, _ = Profile.objects.get_or_create(
        name=user
    )

    # Optional: make sure the URL belongs to the logged-in user
    valid_identifiers = [profile.slug, user.username, str(user.id)]
    if slug and slug not in valid_identifiers and not request.user.is_staff:
        return redirect(
            "profile",
            slug=profile.slug
        )

    if request.method == "POST":

        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        phone = request.POST.get("phone", "").strip()

        # Update first and last name
        user.first_name = first_name
        user.last_name = last_name

        # Username
        if username and username != user.username:

            if User.objects.filter(
                username=username
            ).exclude(
                id=user.id
            ).exists():

                messages.error(
                    request,
                    "Username already taken."
                )

                return redirect(
                    "update",
                    slug=profile.slug
                )

            user.username = username

            # Update slug because username changed
            profile.slug = slugify(username)

        # Email
        if email and email.strip().lower() != (user.email or "").lower():
            clean_email = email.strip().lower()
            if User.objects.filter(email__iexact=clean_email).exclude(id=user.id).exists():
                messages.error(request, "An account with this email already exists.")
                return redirect("update", slug=profile.slug)
            user.email = clean_email

        # Phone
        profile.phone = phone

        # Profile picture
        if "profile_picture" in request.FILES:
            pic = request.FILES["profile_picture"]
            if pic and getattr(pic, "size", 0) > 0:
                is_valid, err = validate_uploaded_image(pic)
                if not is_valid:
                    messages.error(request, f"Profile picture: {err}")
                    return redirect("update", slug=profile.slug)
                profile.profile_picture = pic

        try:
            with transaction.atomic():
                user.save()
                profile.save()
        except Exception as e:
            logger.exception("Failed to update user profile or upload picture: %s", e)
            messages.error(request, f"Failed to save profile changes: {str(e)}")
            return redirect("update", slug=profile.slug)

        messages.success(
            request,
            "Profile updated successfully."
        )

        return redirect(
            "profile",
            slug=profile.slug
        )

    return render(
        request,
        "accounts/update_profile.html",
        {
            "user": user,
            "profile": profile,
        }
    )


@login_required(login_url="login")
def wishlist_view(request):
    wishlist_items = (
        WishList.objects.filter(user=request.user)
        .select_related("product")
        .prefetch_related(
            "product__cat",
            "product__reviews",
            Prefetch(
                "product__variants",
                queryset=ProductVariant.objects.filter(is_active=True).select_related("color", "stock")
            )
        )
        .order_by("-created_at")
    )
    return render(request, "accounts/wishlist.html", {
        "wishlist_items": wishlist_items,
    })


@login_required(login_url="login")
def toggle_wishlist(request, slug):
    product = Product.objects.filter(slug=slug).first()
    if not product and str(slug).isdigit():
        product = Product.objects.filter(id=int(slug)).first()
    if not product:
        messages.error(request, "Product not found.")
        return redirect("wishlist")

    item = WishList.objects.filter(user=request.user, product=product).first()

    if item:
        item.delete()
        messages.info(request, f"Removed {product.name} from your wishlist.")
    else:
        WishList.objects.create(user=request.user, product=product)
        messages.success(request, f"Added {product.name} to your wishlist!")

    next_url = request.POST.get("next") or request.GET.get("next") or request.META.get("HTTP_REFERER")
    if next_url:
        return redirect(next_url)
    return redirect("wishlist")


@login_required(login_url="login")
def remove_from_wishlist(request, slug):
    product = Product.objects.filter(slug=slug).first()
    if not product and str(slug).isdigit():
        product = Product.objects.filter(id=int(slug)).first()
    if not product:
        messages.error(request, "Product not found.")
        return redirect("wishlist")

    WishList.objects.filter(user=request.user, product=product).delete()
    messages.info(request, f"Removed {product.name} from wishlist.")
    return redirect("wishlist")


@login_required(login_url="login")
def address(request):

    if request.method == "POST":

        name = (request.POST.get("full_name") or request.POST.get("name") or "").strip()
        phone = request.POST.get("phone", "").strip()
        address_line = request.POST.get("address_line", "").strip()
        locality = request.POST.get("locality", "").strip()
        landmark = request.POST.get("landmark", "").strip()
        city = request.POST.get("city", "").strip()
        state = request.POST.get("state", "").strip()
        pincode = request.POST.get("pincode", "").strip()
        address_type = request.POST.get("address_type", "HOME")

        # GPS / location tracker fields
        latitude_raw = request.POST.get("latitude", "").strip()
        longitude_raw = request.POST.get("longitude", "").strip()
        area = request.POST.get("area", "").strip()
        formatted_address = request.POST.get("formatted_address", "").strip()

        latitude = None
        longitude = None
        try:
            if latitude_raw:
                latitude = float(latitude_raw)
            if longitude_raw:
                longitude = float(longitude_raw)
        except ValueError:
            pass

        address, created = Address.objects.get_or_create(
            user=request.user,
            address_line=address_line,
            locality=locality,
            city=city,
            state=state,
            pincode=pincode,
            defaults={
                "name": name,
                "phone": phone,
                "landmark": landmark,
                "address_type": address_type,
                "latitude": latitude,
                "longitude": longitude,
                "area": area,
                "formatted_address": formatted_address,
            }
        )

        if created:
            messages.success(
                request,
                "Address added successfully."
            )
        else:
            messages.info(
                request,
                "This address already exists."
            )

        return redirect("address")

    addresses = Address.objects.filter(
        user=request.user
    ).order_by("-id")

    cart_count = get_cart_count(request)


    return render(
        request,
        "accounts/address.html",
        {
            "addresses": addresses,
            'cart_count':cart_count
        }
    )



   
@login_required(login_url="login")
def add_address(request):

    if request.method == "POST":

        name = request.POST.get(
            "name",
            ""
        ).strip()

        phone = request.POST.get(
            "phone",
            ""
        ).strip()

        address_line = request.POST.get(
            "address_line",
            ""
        ).strip()

        locality = request.POST.get(
            "locality",
            ""
        ).strip()

        landmark = request.POST.get(
            "landmark",
            ""
        ).strip()

        city = request.POST.get(
            "city",
            ""
        ).strip()

        state = request.POST.get(
            "state",
            ""
        ).strip()

        pincode = request.POST.get(
            "pincode",
            ""
        ).strip()

        address_type = request.POST.get(
            "address_type",
            "HOME"
        )

        is_default = bool(
            request.POST.get("is_default")
        )

        # If new address is default,
        # remove default from old addresses
        if is_default:
            Address.objects.filter(
                user=request.user
            ).update(
                is_default=False
            )

        # If this is the first address,
        # automatically make it default
        first_address = not Address.objects.filter(
            user=request.user
        ).exists()

        address = Address.objects.create(
            user=request.user,
            name=name,
            phone=phone,
            address_line=address_line,
            locality=locality,
            landmark=landmark,
            city=city,
            state=state,
            pincode=pincode,
            address_type=address_type,
            is_default=is_default or first_address,
        )

        messages.success(
            request,
            "Address saved successfully."
        )

        next_url = (
            request.POST.get("next")
            or request.GET.get("next")
        )

        if next_url:
            return redirect(next_url)

        # Go to profile using slug
        profile = request.user.profile

        return redirect(
            "profile",
            slug=profile.slug
        )

    return redirect("profile")


@login_required(login_url="login")
def delete_address(request, slug):

    if request.method == "POST":

        address = get_object_or_404(
            Address,
            slug=slug,
            user=request.user
        )

        address.delete()

        messages.info(
            request,
            "Address deleted."
        )

    referer = request.META.get("HTTP_REFERER", "")
    if "address" in referer:
        return redirect("address")

    return redirect(
        "profile",
        slug=request.user.profile.slug
    )