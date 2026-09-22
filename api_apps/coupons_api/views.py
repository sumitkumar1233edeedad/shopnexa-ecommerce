from decimal import Decimal

from django.db.models import ProtectedError, Q
from rest_framework import status
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cart.models import Cart
from apps.coupons.models import Coupon
from apps.coupons.services import (
    can_user_use_coupon,
    get_available_coupons,
    get_best_coupon_for_user,
    get_user_weekly_coupon_info,
    validate_coupon_for_user,
)
from .serializers import (
    CouponApplySerializer,
    CouponCreateUpdateSerializer,
    CouponMinimalSerializer,
    CouponSerializer,
    CouponValidationResultSerializer,
    UserWeeklyCouponInfoSerializer,
)


# ==============================================================================
# PERMISSION: ADMIN OR STAFF WITH ASSIGNED PERMISSION ('is_prem' / has_perm)
# ==============================================================================
class IsStaffOrSuperuser(BasePermission):
    """
    Custom permission for Coupon management:
    - Superuser / Admin -> Always allowed.
    - Staff user -> Allowed if they have the specific model permission
      (e.g. 'coupons.add_coupon', 'coupons.change_coupon', 'coupons.delete_coupon')
      or if granted custom 'is_prem' / manager rights.
    - Regular customers -> Rejected with HTTP 403 Forbidden.
    """
    message = "Permission denied. Only administrators or staff members with the required coupon permissions can perform this action."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        # 1. Superuser / Admin -> full unconditional access
        if user.is_superuser:
            return True

        # 2. Staff user or user flagged with custom 'is_prem'
        if user.is_staff or getattr(user, "is_prem", False):
            required_permission = getattr(view, "required_permission", None)

            # If no granular permission specified, any staff member is permitted
            if not required_permission:
                return True

            # Check Django's built-in RBAC permission system (e.g. user.has_perm("coupons.add_coupon"))
            if user.has_perm(required_permission):
                return True

            # If staff has a custom is_prem flag or attribute granted to them
            if getattr(user, "is_prem", False):
                return True

        return False


# ==============================================================================
# HELPER UTILITIES
# ==============================================================================
def _get_cart_subtotal(user):
    """
    Computes current user's active cart subtotal.
    Returns Decimal('0.00') if unauthenticated or empty.
    """
    if not user or not user.is_authenticated:
        return Decimal("0.00")
    cart_obj = Cart.objects.filter(user=user).first()
    if not cart_obj:
        return Decimal("0.00")
    items = cart_obj.items.all()
    if not items.exists():
        return Decimal("0.00")
    return Decimal(str(sum(item.total_price for item in items)))


def _calculate_shipping_fee(subtotal):
    """
    Calculates shipping fee based on cart subtotal:
    Free delivery for orders >= ₹500, otherwise ₹50.
    """
    subtotal_dec = Decimal(str(subtotal or 0))
    if subtotal_dec >= Decimal("500.00") or subtotal_dec <= Decimal("0.00"):
        return Decimal("0.00")
    return Decimal("50.00")


def _get_coupon_by_identifier(identifier):
    """
    Finds coupon by code (case-insensitive), slug, or numeric ID.
    """
    ident_str = str(identifier).strip()
    q = Q(code__iexact=ident_str) | Q(slug=ident_str)
    if ident_str.isdigit():
        q |= Q(id=int(ident_str))
    return Coupon.objects.filter(q).first()


# ==============================================================================
# 1. COUPON LIST & CREATE API VIEW
# ==============================================================================
class CouponListAPIView(APIView):
    """
    GET  /api/coupons/
        - Customer view: Returns active, qualified coupons for active cart.
        - Staff/Admin view (with ?all=true): Returns all coupons in the system.
    POST /api/coupons/
        - Creates a new coupon.
        - Restricted to Superuser or Staff with 'coupons.add_coupon' / is_prem.
    """
    def get_permissions(self):
        if self.request.method == "POST":
            self.required_permission = "coupons.add_coupon"
            return [IsStaffOrSuperuser()]
        return [AllowAny()]

    def get(self, request):
        user = request.user if request.user.is_authenticated else None
        is_staff_user = (
            user and (
                user.is_superuser
                or user.is_staff
                or getattr(user, "is_prem", False)
            )
        )
        include_all = request.query_params.get("all") in ["1", "true", "yes"]

        # Staff/Admin can request all coupons (active, inactive, expired) for administration
        if is_staff_user and include_all:
            all_coupons = Coupon.objects.all().order_by("-created_at")
            serializer = CouponSerializer(
                all_coupons,
                many=True,
                context={"request": request}
            )
            return Response({
                "success": True,
                "is_management_view": True,
                "count": all_coupons.count(),
                "coupons": serializer.data,
            }, status=status.HTTP_200_OK)

        # Standard Customer view: active qualifying coupons
        cart_amount_param = request.query_params.get("cart_amount")
        if cart_amount_param:
            try:
                subtotal = Decimal(str(cart_amount_param))
            except Exception:
                subtotal = _get_cart_subtotal(user)
        else:
            subtotal = _get_cart_subtotal(user)

        coupons = get_available_coupons(user=user, cart_amount=subtotal)
        best_coupon = get_best_coupon_for_user(user=user, cart_amount=subtotal)
        weekly_info = get_user_weekly_coupon_info(user) if user else None

        applied_code = None
        if hasattr(request, "session"):
            applied_code = request.session.get("applied_coupon_code")

        serializer = CouponSerializer(
            coupons,
            many=True,
            context={"request": request, "cart_amount": subtotal}
        )

        return Response({
            "success": True,
            "cart_subtotal": f"{subtotal:.2f}",
            "applied_coupon_code": applied_code,
            "weekly_info": weekly_info,
            "best_coupon": CouponMinimalSerializer(best_coupon).data if best_coupon else None,
            "count": len(coupons),
            "coupons": serializer.data,
        }, status=status.HTTP_200_OK)

    def post(self, request):
        """
        Create a new coupon.
        Restricted to Admin or Staff with 'coupons.add_coupon' / is_prem.
        """
        serializer = CouponCreateUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        coupon = serializer.save()

        return Response({
            "success": True,
            "message": f"Coupon '{coupon.code}' created successfully.",
            "coupon": CouponSerializer(coupon, context={"request": request}).data,
        }, status=status.HTTP_201_CREATED)


# ==============================================================================
# 2. COUPON DETAIL, UPDATE, PATCH & DELETE API VIEW
# ==============================================================================
class CouponDetailAPIView(APIView):
    """
    GET    /api/coupons/<identifier>/ -> Retrieve coupon details (AllowAny)
    PUT    /api/coupons/<identifier>/ -> Full update (Admin or Staff with 'coupons.change_coupon' / is_prem)
    PATCH  /api/coupons/<identifier>/ -> Partial update (Admin or Staff with 'coupons.change_coupon' / is_prem)
    DELETE /api/coupons/<identifier>/ -> Delete or deactivate (Admin or Staff with 'coupons.delete_coupon' / is_prem)
    """
    def get_permissions(self):
        if self.request.method in ("PUT", "PATCH"):
            self.required_permission = "coupons.change_coupon"
            return [IsStaffOrSuperuser()]
        if self.request.method == "DELETE":
            self.required_permission = "coupons.delete_coupon"
            return [IsStaffOrSuperuser()]
        return [AllowAny()]

    def get(self, request, identifier):
        coupon = _get_coupon_by_identifier(identifier)
        if not coupon:
            return Response({
                "success": False,
                "message": f"Coupon '{identifier}' not found."
            }, status=status.HTTP_404_NOT_FOUND)

        subtotal = _get_cart_subtotal(request.user)
        serializer = CouponSerializer(
            coupon,
            context={"request": request, "cart_amount": subtotal}
        )
        return Response({
            "success": True,
            "coupon": serializer.data
        }, status=status.HTTP_200_OK)

    def put(self, request, identifier):
        """
        Full update of a coupon.
        """
        coupon = _get_coupon_by_identifier(identifier)
        if not coupon:
            return Response({
                "success": False,
                "message": f"Coupon '{identifier}' not found."
            }, status=status.HTTP_404_NOT_FOUND)

        serializer = CouponCreateUpdateSerializer(coupon, data=request.data)
        serializer.is_valid(raise_exception=True)
        updated_coupon = serializer.save()

        return Response({
            "success": True,
            "message": f"Coupon '{updated_coupon.code}' updated successfully.",
            "coupon": CouponSerializer(updated_coupon, context={"request": request}).data,
        }, status=status.HTTP_200_OK)

    def patch(self, request, identifier):
        """
        Partial update of a coupon (e.g. toggle is_active, update valid_until, etc.).
        """
        coupon = _get_coupon_by_identifier(identifier)
        if not coupon:
            return Response({
                "success": False,
                "message": f"Coupon '{identifier}' not found."
            }, status=status.HTTP_404_NOT_FOUND)

        serializer = CouponCreateUpdateSerializer(coupon, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated_coupon = serializer.save()

        return Response({
            "success": True,
            "message": f"Coupon '{updated_coupon.code}' updated successfully.",
            "coupon": CouponSerializer(updated_coupon, context={"request": request}).data,
        }, status=status.HTTP_200_OK)

    def delete(self, request, identifier):
        """
        Delete a coupon.
        If the coupon has existing order usages, it cannot be hard deleted due to database
        protection (PROTECT). It will be safely deactivated instead.
        """
        coupon = _get_coupon_by_identifier(identifier)
        if not coupon:
            return Response({
                "success": False,
                "message": f"Coupon '{identifier}' not found."
            }, status=status.HTTP_404_NOT_FOUND)

        code = coupon.code
        try:
            coupon.delete()
            return Response({
                "success": True,
                "deleted": True,
                "message": f"Coupon '{code}' deleted successfully."
            }, status=status.HTTP_200_OK)
        except ProtectedError:
            # Safely deactivate coupon when order usages exist
            coupon.is_active = False
            coupon.save()
            return Response({
                "success": True,
                "deleted": False,
                "deactivated": True,
                "message": f"Coupon '{code}' has existing order usages and cannot be permanently deleted. It has been deactivated instead."
            }, status=status.HTTP_200_OK)


# ==============================================================================
# 3. APPLY COUPON API VIEW (Cart / Checkout Session)
# ==============================================================================
class CouponApplyAPIView(APIView):
    """
    POST /api/coupons/apply/
    Applies a coupon to the user's active checkout session.
    Payload:
        { "code": "SAVE20" }  OR  { "auto_apply": true }
        Optional: { "order_amount": "1200.00" }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CouponApplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        coupon_code = data.get("code", "")
        is_auto_apply = data.get("auto_apply", False)
        order_amount_input = data.get("order_amount")

        # Determine subtotal (from input or user's active cart)
        subtotal = (
            order_amount_input
            if order_amount_input is not None
            else _get_cart_subtotal(request.user)
        )

        if subtotal <= Decimal("0.00"):
            return Response({
                "success": False,
                "message": "Your cart is empty."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Handle auto-apply
        if is_auto_apply and not coupon_code:
            best = get_best_coupon_for_user(request.user, subtotal)
            if not best:
                return Response({
                    "success": False,
                    "message": "No eligible coupon available to auto-apply for your cart amount."
                }, status=status.HTTP_400_BAD_REQUEST)
            coupon_code = best.code

        if not coupon_code:
            return Response({
                "success": False,
                "message": "Please enter a coupon code."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate coupon with full business logic
        is_valid, error_msg, coupon, discount = validate_coupon_for_user(
            coupon_code=coupon_code,
            user=request.user,
            order_amount=subtotal
        )

        if not is_valid or not coupon:
            return Response({
                "success": False,
                "message": error_msg or "Invalid coupon."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Persist applied coupon into session for checkout/order placement
        if hasattr(request, "session"):
            request.session["applied_coupon_code"] = coupon.code

        shipping_fee = _calculate_shipping_fee(subtotal)
        discounted_subtotal = max(Decimal("0.00"), subtotal - discount)
        new_total = discounted_subtotal + shipping_fee
        weekly_info = get_user_weekly_coupon_info(request.user, coupon=coupon)

        return Response({
            "success": True,
            "message": f"✓ {coupon.code} applied successfully!",
            "coupon_code": coupon.code,
            "coupon": CouponMinimalSerializer(coupon).data,
            "discount_amount": f"{discount:.2f}",
            "subtotal": f"{subtotal:.2f}",
            "shipping_fee": f"{shipping_fee:.2f}",
            "total": f"{new_total:.2f}",
            "weekly_usage": f"{weekly_info['usage_count']} / {weekly_info['weekly_limit']}",
            "remaining_uses": weekly_info["remaining"],
        }, status=status.HTTP_200_OK)


# ==============================================================================
# 4. REMOVE COUPON API VIEW (Cart / Checkout Session)
# ==============================================================================
class CouponRemoveAPIView(APIView):
    """
    POST /api/coupons/remove/
    Removes the currently applied coupon from the user's active session.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        removed_code = None
        if hasattr(request, "session"):
            removed_code = request.session.pop("applied_coupon_code", None)

        # Allow optional order_amount from request body/params or fallback to active cart
        order_amount_input = request.data.get("order_amount") or request.query_params.get("order_amount")
        if order_amount_input is not None:
            try:
                subtotal = Decimal(str(order_amount_input))
            except Exception:
                subtotal = _get_cart_subtotal(request.user)
        else:
            subtotal = _get_cart_subtotal(request.user)

        shipping_fee = _calculate_shipping_fee(subtotal)
        new_total = subtotal + shipping_fee
        weekly_info = get_user_weekly_coupon_info(request.user)

        msg = f"Coupon {removed_code} removed." if removed_code else "No coupon applied."

        return Response({
            "success": True,
            "message": msg,
            "removed_code": removed_code,
            "coupon_code": None,
            "coupon": None,
            "discount_amount": "0.00",
            "subtotal": f"{subtotal:.2f}",
            "shipping_fee": f"{shipping_fee:.2f}",
            "total": f"{new_total:.2f}",
            "weekly_usage": f"{weekly_info['usage_count']} / {weekly_info['weekly_limit']}",
            "remaining_uses": weekly_info["remaining"],
        }, status=status.HTTP_200_OK)


# ==============================================================================
# 5. PREVIEW / CHECK COUPON API VIEW (Stateless Dry-run)
# ==============================================================================
class CouponCheckAPIView(APIView):
    """
    POST /api/coupons/check/
    Statelessly validates a coupon code against a subtotal or current cart,
    without storing it into the session.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CouponApplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        coupon_code = data.get("code", "")
        is_auto_apply = data.get("auto_apply", False)
        order_amount_input = data.get("order_amount")

        subtotal = (
            order_amount_input
            if order_amount_input is not None
            else _get_cart_subtotal(request.user)
        )

        if is_auto_apply and not coupon_code:
            best = get_best_coupon_for_user(request.user, subtotal)
            if not best:
                return Response({
                    "is_valid": False,
                    "message": "No eligible coupon available for this cart amount.",
                    "coupon": None,
                    "order_amount": f"{subtotal:.2f}",
                    "discount_amount": "0.00",
                    "final_amount": f"{subtotal:.2f}",
                    "weekly_info": get_user_weekly_coupon_info(request.user),
                }, status=status.HTTP_200_OK)
            coupon_code = best.code

        is_valid, msg, coupon, discount = validate_coupon_for_user(
            coupon_code=coupon_code,
            user=request.user,
            order_amount=subtotal
        )

        final_amount = max(Decimal("0.00"), subtotal - discount)
        weekly_info = get_user_weekly_coupon_info(request.user, coupon=coupon)

        result_serializer = CouponValidationResultSerializer({
            "is_valid": is_valid,
            "message": msg or "Coupon is valid.",
            "coupon": CouponMinimalSerializer(coupon).data if coupon else None,
            "order_amount": subtotal,
            "discount_amount": discount,
            "final_amount": final_amount,
            "weekly_info": weekly_info,
        })
        return Response(result_serializer.data, status=status.HTTP_200_OK)


# ==============================================================================
# 6. USER WEEKLY COUPON QUOTA STATUS API VIEW
# ==============================================================================
class UserWeeklyCouponStatusAPIView(APIView):
    """
    GET /api/coupons/weekly-status/
    Returns the authenticated user's weekly coupon quota statistics.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        weekly_info = get_user_weekly_coupon_info(request.user)
        serializer = UserWeeklyCouponInfoSerializer(weekly_info)
        return Response({
            "success": True,
            "weekly_info": serializer.data
        }, status=status.HTTP_200_OK)
