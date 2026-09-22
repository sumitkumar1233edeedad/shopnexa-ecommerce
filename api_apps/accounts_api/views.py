from django.shortcuts import render
import re
# Create your views here.
from apps.accounts.tasks import validate_user_email, generate_and_send_otp, send_registration_email
from django.contrib.auth import authenticate, get_user_model, login, logout, update_session_auth_hash
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.authtoken.models import Token
from django.utils import timezone
from datetime import timedelta
from django.db import transaction
from apps.accounts.models import *
from apps.cart.models import Cart, CartItem
from apps.products.models import *
from apps.products.validators import validate_uploaded_image
from apps.order.models import *
User = get_user_model()
from rest_framework.permissions import IsAuthenticated
from .serializers import *




def merge_session_cart_to_user(request, user):
    """
    Move guest/session cart into the logged-in user's database cart.

    Session cart format:

    {
        "black-tshirt-large": {
            "quantity": 2
        }
    }

    If the same variant already exists in the database cart,
    quantities are added together.
    """

    session_cart = request.session.get("cart", {})

    if not session_cart:
        return

    cart_obj, _ = Cart.objects.get_or_create(user=user)

    with transaction.atomic():

        for variant_slug, data in list(session_cart.items()):

            # Find variant by slug
            variant = ProductVariant.objects.filter(
                slug=variant_slug,
                is_active=True
            ).first()

            # Variant no longer exists / inactive
            if not variant:
                continue

            # Support both:
            # {"quantity": 2}
            # 2
            if isinstance(data, dict):
                quantity = data.get("quantity", 1)
            else:
                quantity = data

            try:
                quantity = int(quantity)
            except (ValueError, TypeError):
                quantity = 1

            if quantity < 1:
                continue

            # Check if variant already exists in user's cart
            item, created = CartItem.objects.get_or_create(
                cart=cart_obj,
                product=variant,
                defaults={
                    "quantity": quantity
                }
            )

            if not created:
                item.quantity += quantity
                item.save(update_fields=["quantity"])

    # Clear guest cart after successful merge
    request.session["cart"] = {}
    request.session.modified = True



class LoginAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):

        username_or_email = request.data.get("username", "").strip()
        password = request.data.get("password", "")

        if not username_or_email or not password:
            return Response(
                {
                    "success": False,
                    "message": "Username/email and password are required."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Find user by username
        user_obj = User.objects.filter(
            username__iexact=username_or_email
        ).first()

        # If not found, find by email
        if not user_obj:
            user_obj = User.objects.filter(
                email__iexact=username_or_email
            ).first()

        # User doesn't exist or password incorrect
        if not user_obj or not user_obj.check_password(password):
            return Response(
                {
                    "success": False,
                    "message": "Invalid username/email or password."
                },
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Email not verified
        if not user_obj.is_active:
            return Response(
                {
                    "success": False,
                    "verified": False,
                    "message": "Please verify your email first.",
                    "user_id": user_obj.id
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # Authenticate
        user = authenticate(
            request=request,
            username=user_obj.username,
            password=password
        )

        if user is None:
            return Response(
                {
                    "success": False,
                    "message": "Authentication failed."
                },
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Create/get token
        token, created = Token.objects.get_or_create(user=user)

        # Merge guest cart into user's database cart
        # Supports session cart (web) and request body 'cart' payload (mobile/SPA)
        try:
            payload_cart = request.data.get("cart") or request.data.get("session_cart")
            if payload_cart:
                if not hasattr(request, "session"):
                    request.session = {}
                session_cart = request.session.get("cart", {})
                if isinstance(payload_cart, list):
                    for item in payload_cart:
                        slug = item.get("variant_slug") or item.get("slug")
                        qty = item.get("quantity", 1)
                        if slug:
                            try:
                                qty = int(qty)
                            except (ValueError, TypeError):
                                qty = 1
                            current = session_cart.get(slug, {}).get("quantity", 0) if isinstance(session_cart.get(slug), dict) else 0
                            session_cart[slug] = {"quantity": current + qty}
                elif isinstance(payload_cart, dict):
                    for slug, data in payload_cart.items():
                        qty = data.get("quantity", 1) if isinstance(data, dict) else data
                        try:
                            qty = int(qty)
                        except (ValueError, TypeError):
                            qty = 1
                        current = session_cart.get(slug, {}).get("quantity", 0) if isinstance(session_cart.get(slug), dict) else 0
                        session_cart[slug] = {"quantity": current + qty}
                request.session["cart"] = session_cart

            merge_session_cart_to_user(request, user)
        except Exception:
            pass

        cart_obj = Cart.objects.filter(user=user).first()
        cart_total_items = cart_obj.total_items if cart_obj else 0
        cart_total_price = str(cart_obj.total_price) if cart_obj else "0.00"

        return Response(
            {
                "success": True,
                "message": "Login successful.",
                "token": token.key,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "is_staff": user.is_staff,
                },
                "cart": {
                    "total_items": cart_total_items,
                    "total_price": cart_total_price,
                },
            },
            status=status.HTTP_200_OK
        )


class LogoutAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        return self._logout(request)

    def get(self, request):
        return self._logout(request)

    def _logout(self, request):
        # 1. Delete DRF auth token if present
        try:
            if hasattr(request.user, "auth_token"):
                request.user.auth_token.delete()
            else:
                Token.objects.filter(user=request.user).delete()
        except Exception:
            pass

        # 2. Flush Django session
        logout(request)

        return Response(
            {
                "success": True,
                "message": "Logged out successfully."
            },
            status=status.HTTP_200_OK
        )


class RegisterAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        if request.user.is_authenticated:
            return Response({"success": True, "message": "Already logged in"},status=status.HTTP_200_OK)

         
        first_name = request.data.get("first_name", "").strip()
        last_name = request.data.get("last_name", "").strip()
        email = request.data.get("email", "").strip().lower()
        password = request.data.get("password")
        confirm_password = request.data.get("confirm_password")

        # 1. Check required fields and passwords
        if not first_name:
            
            return Response({"success": False, "message": "First name is required."}, status=status.HTTP_400_BAD_REQUEST)

        if password != confirm_password:
            
            return Response({"success": False, "message": "Passwords do not match."}, status=status.HTTP_400_BAD_REQUEST)

        if len(password) < 6:
            
            return Response({"success": False, "message": "Password must be at least 6 characters long."}, status=status.HTTP_400_BAD_REQUEST)

        # 2. Strict Email Validation
        is_valid_email, email_error = validate_user_email(email)
        if not is_valid_email:
                
            return Response({"success": False, "message": email_error}, status=status.HTTP_400_BAD_REQUEST)

        # 3. Check active user with same email
        if User.objects.filter(email__iexact=email, is_active=True).exists():
            return Response({'success':False, 'message':'An account with this email already exists. Please log in or reset your password.'}, status=status.HTTP_409_CONFLICT)

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
            is_active=False
        )

        token, created = Token.objects.get_or_create(user=user)


        # 6. Send OTP Email
        try:
            generate_and_send_otp(user, purpose="registration")
            request.session["otp_user_id"] = user.id
            
            return Response(
            {
                "success": True,
                "token": token.key,
                "message": (
                    f"A 6-digit verification code has been "
                    f"sent to {email}. Valid for 10 minutes."
                ),
                "data": {
                    "user_id": user.id,
                    "username": user.username,
                    "email": user.email
                }
            },
            status=status.HTTP_201_CREATED
        )
        except Exception as e:
            user.delete()
            return Response(
                {
                    "success": False,
                    "message": "Failed to send verification email.",
                    "error": str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class VerifyOTPAPIView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        # Get user ID from session
        user_id = request.session.get("otp_user_id")
        if not user_id:
            return Response(
                {
                    "success": False,
                    "message": "Session expired or invalid. Please register again."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get user
        user = get_object_or_404(User, id=user_id)

        # Get OTP from JSON request
        entered_otp = str(request.data.get("otp", "")).strip()
        if not entered_otp:
            return Response(
                {
                    "success": False,
                    "message": "Please enter the 6-digit OTP code."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check OTP length
        if len(entered_otp) != 6 or not entered_otp.isdigit():
            return Response(
                {
                    "success": False,
                    "message": "OTP must be a 6-digit number."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check OTP
        if not user.temp_otp or user.temp_otp != entered_otp:
            return Response(
                {
                    "success": False,
                    "message": "Invalid OTP code. Please check your email and try again."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check OTP expiry
        if (
            user.otp_created_at and 
            timezone.now() > user.otp_created_at + timedelta(minutes=10)
        ):
            return Response(
                {
                    "success": False,
                    "message": "This OTP has expired. Please request a new OTP."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Verify and activate user
        user.temp_otp = None
        user.otp_created_at = None
        user.is_email_verified = True
        user.is_activated = True
        user.is_active = True
        user.save(
            update_fields=[
                "temp_otp",
                "otp_created_at",
                "is_email_verified",
                "is_activated",
                "is_active",
            ]
        )

        # Create profile after successful verification
        Profile.objects.get_or_create(name=user)

        # Send welcome email only after successful database commit
        transaction.on_commit(lambda: send_registration_email.delay(user.id))

        # Login user
        login(request, user)

        # Merge guest cart with user's cart
        try:
            merge_session_cart_to_user(request, user)
        except Exception:
            pass

        # Remove OTP user session
        request.session.pop("otp_user_id", None)

        return Response(
            {
                "success": True,
                "message": "Email verified successfully! Welcome to AI Store.",
                "data": {
                    "user_id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "is_email_verified": user.is_email_verified,
                    "is_activated": user.is_activated,
                    "is_active": user.is_active,
                }
            },
            status=status.HTTP_200_OK
        )   

 
class ForgotPasswordAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):

        email = request.data.get("email", "").strip().lower()

        # 1. Validate email
        is_valid_email, email_error = validate_user_email(email)

        if not is_valid_email:
            return Response(
                {
                    "success": False,
                    "message": email_error
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2. Find active user
        user = User.objects.filter(
            email__iexact=email,
            is_active=True
        ).first()

        if not user:
            return Response(
                {
                    "success": False,
                    "message": "No active account found with this email address."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # 3. Generate and send OTP
        try:
            generate_and_send_otp(
                user,
                purpose="password_reset"
            )

            # Store user ID in session for OTP verification
            request.session["reset_user_id"] = user.id
            request.session["reset_otp_verified"] = False

            return Response(
                {
                    "success": True,
                    "message": (
                        f"A 6-digit password reset code has been "
                        f"sent to {email}. Valid for 10 minutes."
                    ),
                    "data": {
                        "user_id": user.id,
                        "email": user.email
                    }
                },
                status=status.HTTP_200_OK
            )

        except Exception as e:
            return Response(
                {
                    "success": False,
                    "message": "Failed to send reset email.",
                    "error": str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class VerifyResetOTPAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):

        # 1. Get user ID from session
        user_id = request.session.get("reset_user_id")

        if not user_id:
            return Response(
                {
                    "success": False,
                    "message": "Session expired. Please enter your email again."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2. Get user
        user = get_object_or_404(User, id=user_id)

        # 3. Get OTP from JSON
        entered_otp = str(request.data.get("otp", "")).strip()

        if not entered_otp:
            return Response(
                {
                    "success": False,
                    "message": "Please enter the 6-digit reset code."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # 4. Validate OTP format
        if len(entered_otp) != 6 or not entered_otp.isdigit():
            return Response(
                {
                    "success": False,
                    "message": "OTP must be a 6-digit number."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # 5. Check OTP
        if not user.temp_otp or user.temp_otp != entered_otp:
            return Response(
                {
                    "success": False,
                    "message": "Invalid reset code. Please check your email and try again."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # 6. Check OTP expiry
        if (
            user.otp_created_at
            and timezone.now() >
            user.otp_created_at + timedelta(minutes=10)
        ):
            return Response(
                {
                    "success": False,
                    "message": (
                        "This reset code has expired. "
                        "Please request a new one."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # 7. Clear OTP after successful verification
        user.temp_otp = None
        user.otp_created_at = None

        user.save(
            update_fields=[
                "temp_otp",
                "otp_created_at"
            ]
        )

        # 8. Mark OTP as verified
        request.session["reset_otp_verified"] = True

        return Response(
            {
                "success": True,
                "message": "OTP verified successfully. Please set your new password.",
                "data": {
                    "user_id": user.id,
                    "email": user.email
                }
            },
            status=status.HTTP_200_OK
        )
 
 
class ResendResetOTPAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):

        # 1. Get user ID from session
        user_id = request.session.get("reset_user_id")

        if not user_id:
            return Response(
                {
                    "success": False,
                    "message": "Session expired. Please start over."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2. Get user
        user = get_object_or_404(User, id=user_id)

        # 3. Generate and send new OTP
        try:
            generate_and_send_otp(
                user,
                purpose="password_reset"
            )

            return Response(
                {
                    "success": True,
                    "message": f"A new reset code has been sent to {user.email}.",
                    "data": {
                        "user_id": user.id,
                        "email": user.email
                    }
                },
                status=status.HTTP_200_OK
            )

        except Exception as e:
            return Response(
                {
                    "success": False,
                    "message": "Failed to resend reset code.",
                    "error": str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class ResetPasswordAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):

        # 1. Get user ID and OTP verification status from session
        user_id = request.session.get("reset_user_id")
        is_verified = request.session.get("reset_otp_verified", False)

        if not user_id or not is_verified:
            return Response(
                {
                    "success": False,
                    "message": (
                        "Unauthorized access or session expired. "
                        "Please verify your OTP first."
                    )
                },
                status=status.HTTP_401_UNAUTHORIZED
            )

        # 2. Get user
        user = get_object_or_404(User, id=user_id)

        # 3. Get passwords from JSON
        new_password = request.data.get("new_password")
        confirm_password = request.data.get("confirm_password")

        if not new_password or not confirm_password:
            return Response(
                {
                    "success": False,
                    "message": "New password and confirm password are required."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # 4. Check password match
        if new_password != confirm_password:
            return Response(
                {
                    "success": False,
                    "message": "Passwords do not match."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # 5. Check password length
        if len(new_password) < 6:
            return Response(
                {
                    "success": False,
                    "message": "Password must be at least 6 characters long."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # 6. Set new password
        user.set_password(new_password)

        user.is_email_verified = True
        user.is_activated = True
        user.is_active = True
        user.temp_otp = None
        user.otp_created_at = None

        user.save(
            update_fields=[
                "password",
                "is_email_verified",
                "is_activated",
                "is_active",
                "temp_otp",
                "otp_created_at",
            ]
        )

        # 7. Clear reset session
        request.session.pop("reset_user_id", None)
        request.session.pop("reset_otp_verified", None)

        # 8. If already authenticated, update session auth hash
        if request.user.is_authenticated:
            update_session_auth_hash(request, user)

            return Response(
                {
                    "success": True,
                    "message": "Your password has been updated successfully."
                },
                status=status.HTTP_200_OK
            )

        # 9. Otherwise tell user to login
        return Response(
            {
                "success": True,
                "message": (
                    "Password changed successfully. "
                    "You can now log in with your new password."
                )
            },
            status=status.HTTP_200_OK
        )
 

class ProfileAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def _resolve_target(self, request, slug=None):
        """
        Helper method to resolve target user and target profile based on slug and permissions.
        Returns (target_user, target_profile, error_response)
        """
        user = request.user
        profile, _ = Profile.objects.get_or_create(name=user)

        if not slug:
            return user, profile, None

        valid_identifiers = [
            profile.slug,
            user.username,
            str(user.id),
        ]

        if slug in valid_identifiers:
            return user, profile, None

        if not user.is_staff:
            return None, None, Response(
                {
                    "success": False,
                    "message": "You can only access your own profile.",
                    "profile_slug": profile.slug,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # Staff looking up another user's profile
        target_profile = (
            Profile.objects.filter(slug=slug).first()
            or Profile.objects.filter(name__username=slug).first()
        )
        if not target_profile and slug.isdigit():
            target_profile = Profile.objects.filter(name__id=int(slug)).first()

        if not target_profile:
            return None, None, Response(
                {
                    "success": False,
                    "message": "Profile not found."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        return target_profile.name, target_profile, None

    def get(self, request, slug=None):
        target_user, target_profile, error_response = self._resolve_target(request, slug)
        if error_response:
            return error_response

        profile_serializer = ProfileSerializer(
            target_profile,
            context={"request": request}
        )

        # Addresses
        addresses = Address.objects.filter(
            user=target_user
        ).order_by(
            "-is_default",
            "-id"
        )
        address_serializer = AddressSerializer(
            addresses,
            many=True,
            context={"request": request}
        )

        # Wishlist
        wishlist_items = WishList.objects.filter(
            user=target_user
        ).select_related(
            "product"
        )[:4]
        wishlist_serializer = WishListSerializer(
            wishlist_items,
            many=True,
            context={"request": request}
        )

        orders_count = Order.objects.filter(
            user=target_user
        ).count()
        wishlist_count = WishList.objects.filter(
            user=target_user
        ).count()
        addresses_count = addresses.count()

        return Response(
            {
                "success": True,
                "profile": profile_serializer.data,
                "addresses": address_serializer.data,
                "wishlist_items": wishlist_serializer.data,
                "counts": {
                    "orders": orders_count,
                    "wishlist": wishlist_count,
                    "addresses": addresses_count,
                },
            },
            status=status.HTTP_200_OK,
        )

    def put(self, request, slug=None):
        return self.patch(request, slug)

    def patch(self, request, slug=None):
        target_user, target_profile, error_response = self._resolve_target(request, slug)
        if error_response:
            return error_response

        # Image validation if uploaded
        profile_picture = request.FILES.get("profile_picture")
        if profile_picture:
            is_valid, img_error = validate_uploaded_image(profile_picture)
            if not is_valid:
                return Response(
                    {
                        "success": False,
                        "message": img_error
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        serializer = ProfileSerializer(
            target_profile,
            data=request.data,
            partial=True,
            context={"request": request}
        )
        if serializer.is_valid():
            serializer.save()
            return Response(
                {
                    "success": True,
                    "message": "Profile updated successfully.",
                    "profile": serializer.data,
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                "success": False,
                "message": "Profile update failed.",
                "errors": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


# =========================================================
# WISHLIST API VIEW (UNIFIED)
# =========================================================

class WishListAPIView(APIView):
     
    permission_classes = [IsAuthenticated]

    def _get_product(self, request, slug=None):
        identifier = (
            slug
            or request.data.get("slug")
            or request.data.get("product_id")
            or request.data.get("product")
        )
        if not identifier:
            return None, None, Response(
                {
                    "success": False,
                    "message": "Product slug or ID is required.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        product = Product.objects.filter(slug=str(identifier)).first()
        if not product and str(identifier).isdigit():
            product = Product.objects.filter(id=int(identifier)).first()

        wishlist_item = None
        if not product:
            wishlist_item = WishList.objects.filter(
                user=request.user, slug=str(identifier)
            ).first()
            if wishlist_item:
                product = wishlist_item.product

        if not product and not wishlist_item:
            return None, None, Response(
                {
                    "success": False,
                    "message": "Product not found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        return product, wishlist_item, None

    def get(self, request):
        wishlist_items = (
            WishList.objects.filter(user=request.user)
            .select_related("product")
            .order_by("-created_at")
        )
        serializer = WishListSerializer(
            wishlist_items,
            many=True,
            context={"request": request}
        )
        return Response(
            {
                "success": True,
                "count": wishlist_items.count(),
                "wishlist_items": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request, slug=None):
        product, _, error_response = self._get_product(request, slug)
        if error_response:
            return error_response

        item = WishList.objects.filter(user=request.user, product=product).first()
        if item:
            item.delete()
            return Response(
                {
                    "success": True,
                    "is_in_wishlist": False,
                    "action": "removed",
                    "message": f"Removed {product.name} from your wishlist.",
                },
                status=status.HTTP_200_OK,
            )
        else:
            new_item = WishList.objects.create(user=request.user, product=product)
            serializer = WishListSerializer(new_item, context={"request": request})
            return Response(
                {
                    "success": True,
                    "is_in_wishlist": True,
                    "action": "added",
                    "message": f"Added {product.name} to your wishlist!",
                    "item": serializer.data,
                },
                status=status.HTTP_201_CREATED,
            )

    def delete(self, request, slug=None):
        product, wishlist_item, error_response = self._get_product(request, slug)
        if error_response:
            return error_response

        deleted_count, _ = WishList.objects.filter(
            user=request.user, product=product
        ).delete()
        if deleted_count == 0 and not wishlist_item:
            return Response(
                {
                    "success": False,
                    "message": f"{product.name} is not in your wishlist.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        product_name = product.name if product else "Product"
        return Response(
            {
                "success": True,
                "is_in_wishlist": False,
                "action": "removed",
                "message": f"Removed {product_name} from wishlist.",
            },
            status=status.HTTP_200_OK,
        )


# Backward-compatible aliases
ToggleWishListAPIView = WishListAPIView
RemoveFromWishListAPIView = WishListAPIView



# =========================================================
# ADDRESS API VIEW (UNIFIED)
# =========================================================

class AddressAPIView(APIView):
    
    permission_classes = [IsAuthenticated]

    def _get_address(self, request, slug):
        address = Address.objects.filter(
            user=request.user,
            slug=str(slug)
        ).first()

        if not address and str(slug).isdigit():
            address = Address.objects.filter(
                user=request.user,
                id=int(slug)
            ).first()

        return address

     
    def get(self, request, slug=None):
        if slug is None:
            addresses = Address.objects.filter(
                user=request.user
            ).order_by("-is_default", "-id")

            serializer = AddressSerializer(
                addresses,
                many=True,
                context={"request": request}
            )

            return Response(
                {
                    "success": True,
                    "count": addresses.count(),
                    "addresses": serializer.data,
                },
                status=status.HTTP_200_OK,
            )

        address = self._get_address(request, slug)
        if not address:
            return Response(
                {
                    "success": False,
                    "message": "Address not found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = AddressSerializer(
            address,
            context={"request": request}
        )
        return Response(
            {
                "success": True,
                "address": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

     
    def post(self, request, slug=None):
        # 1. /addresses/<slug>/set-default/
        if slug and (request.path.rstrip("/").endswith("/set-default") or "set-default" in request.path):
            address = self._get_address(request, slug)
            if not address:
                return Response(
                    {
                        "success": False,
                        "message": "Address not found.",
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

            with transaction.atomic():
                Address.objects.filter(user=request.user).update(is_default=False)
                address.is_default = True
                address.save(update_fields=["is_default"])

            serializer = AddressSerializer(
                address,
                context={"request": request}
            )
            return Response(
                {
                    "success": True,
                    "message": "Address set as default successfully.",
                    "address": serializer.data,
                },
                status=status.HTTP_200_OK,
            )

        # 2. /addresses/<slug>/delete/ or /addresses/delete/<slug>/
        if slug and (request.path.rstrip("/").endswith("/delete") or "/delete/" in request.path):
            return self.delete(request, slug)

        
        is_default = bool(request.data.get("is_default"))
        first_address = not Address.objects.filter(user=request.user).exists()
        if first_address:
            is_default = True

        serializer = AddressSerializer(
            data=request.data,
            context={"request": request}
        )

        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "message": "Address validation failed.",
                    "errors": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            if is_default:
                Address.objects.filter(user=request.user).update(is_default=False)

            address = serializer.save(
                user=request.user,
                is_default=is_default
            )

        return Response(
            {
                "success": True,
                "message": "Address saved successfully.",
                "address": AddressSerializer(
                    address,
                    context={"request": request}
                ).data,
            },
            status=status.HTTP_201_CREATED,
        )

  
    def put(self, request, slug):
        return self.patch(request, slug)

   
    def patch(self, request, slug):
        address = self._get_address(request, slug)
        if not address:
            return Response(
                {
                    "success": False,
                    "message": "Address not found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = AddressSerializer(
            address,
            data=request.data,
            partial=True,
            context={"request": request}
        )

        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "message": "Address update failed.",
                    "errors": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            is_default_input = request.data.get("is_default")
            if is_default_input is not None and bool(is_default_input):
                Address.objects.filter(
                    user=request.user
                ).exclude(pk=address.pk).update(is_default=False)

            address = serializer.save()

        return Response(
            {
                "success": True,
                "message": "Address updated successfully.",
                "address": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


    def delete(self, request, slug):
        address = self._get_address(request, slug)
        if not address:
            return Response(
                {
                    "success": False,
                    "message": "Address not found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        was_default = address.is_default
        address.delete()

        if was_default:
            next_address = Address.objects.filter(
                user=request.user
            ).order_by("-id").first()

            if next_address:
                next_address.is_default = True
                next_address.save(update_fields=["is_default"])

        return Response(
            {
                "success": True,
                "message": "Address deleted successfully.",
            },
            status=status.HTTP_200_OK,
        )


# Backward-compatible aliases
AddressListCreateAPIView = AddressAPIView
AddressDetailAPIView = AddressAPIView
AddressDeleteAPIView = AddressAPIView
SetDefaultAddressAPIView = AddressAPIView






