import logging
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.shortcuts import get_object_or_404
from django.db.models import Q
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .permissions import IsSuperAdminUser
from .serializers import (
    AdminUserCreateSerializer,
    AdminUserSerializer,
    AdminUserUpdateSerializer,
    NonStaffUserSerializer,
    PermissionSerializer,
    StaffAddSerializer,
    StaffPermissionsUpdateSerializer,
    StaffUserSerializer,
)

logger = logging.getLogger(__name__)
User = get_user_model()

# Apps whose model permissions can be delegated to store staff
STORE_APPS = ["products", "coupons", "order", "chat", "accounts"]


def get_store_permissions():
    """
    Fetch all Permission records belonging to store applications:
    products, coupons, order, chat, accounts.
    Ordered by app_label and permission name.
    """
    return (
        Permission.objects
        .filter(content_type__app_label__in=STORE_APPS)
        .select_related("content_type")
        .order_by("content_type__app_label", "name")
    )


def _extract_permission_ids(request):
    """
    Robustly extract permission IDs from request data, supporting:
    - JSON array: {"permissions": [1, 2, 3]}
    - Multi-value form-data: request.data.getlist("permissions")
    - Comma-separated string: "1,2,3"
    - Single integer or string
    """
    raw_perms = None
    if hasattr(request.data, "getlist"):
        list_val = request.data.getlist("permissions")
        if list_val:
            raw_perms = list_val

    if raw_perms is None:
        raw_perms = request.data.get("permissions", [])

    if isinstance(raw_perms, str):
        raw_perms = [p.strip() for p in raw_perms.split(",") if p.strip()]
    elif not isinstance(raw_perms, (list, tuple, set)):
        raw_perms = [raw_perms] if raw_perms is not None else []

    perm_ids = []
    for item in raw_perms:
        try:
            perm_ids.append(int(item))
        except (ValueError, TypeError):
            continue
    return perm_ids


# ==============================================================================
# 1. STAFF LIST API VIEW
# ==============================================================================
class StaffListAPIView(APIView):
    """
    GET /api/admin/staff/

    List all staff members and their active permissions.
    Only superadmins can access this view.
    """
    permission_classes = [IsAuthenticated, IsSuperAdminUser]

    def get(self, request):
        staff_members = (
            User.objects
            .filter(is_staff=True)
            .prefetch_related("user_permissions__content_type")
            .order_by("username")
        )
        serializer = StaffUserSerializer(staff_members, many=True)
        return Response({
            "success": True,
            "count": staff_members.count(),
            "staff_members": serializer.data
        }, status=status.HTTP_200_OK)


# ==============================================================================
# 2. STAFF PERMISSIONS API VIEW
# ==============================================================================
class StaffPermissionsAPIView(APIView):
    """
    GET  /api/admin/staff/<user_id>/permissions/
    POST /api/admin/staff/<user_id>/permissions/
    PUT  /api/admin/staff/<user_id>/permissions/

    Configure specific permissions for a staff member.
    Only superadmins can access this view.
    """
    permission_classes = [IsAuthenticated, IsSuperAdminUser]

    def get(self, request, user_id):
        staff_user = get_object_or_404(
            User.objects.prefetch_related("user_permissions__content_type"),
            id=user_id,
            is_staff=True
        )

        permissions = get_store_permissions()
        user_perm_ids = set(staff_user.user_permissions.values_list("id", flat=True))

        return Response({
            "success": True,
            "staff_user": StaffUserSerializer(staff_user).data,
            "user_perm_ids": sorted(list(user_perm_ids)),
            "available_permissions": PermissionSerializer(permissions, many=True).data,
        }, status=status.HTTP_200_OK)

    def post(self, request, user_id):
        return self._update_permissions(request, user_id)

    def put(self, request, user_id):
        return self._update_permissions(request, user_id)

    def _update_permissions(self, request, user_id):
        staff_user = get_object_or_404(User, id=user_id, is_staff=True)

        selected_perm_ids = _extract_permission_ids(request)

        serializer = StaffPermissionsUpdateSerializer(data={"permissions": selected_perm_ids})
        if not serializer.is_valid():
            return Response({
                "success": False,
                "message": "Validation error.",
                "errors": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        valid_perm_ids = serializer.validated_data["permissions"]
        staff_user.user_permissions.set(valid_perm_ids)

        return Response({
            "success": True,
            "message": f"Permissions updated successfully for {staff_user.username}.",
            "staff_user": StaffUserSerializer(staff_user).data
        }, status=status.HTTP_200_OK)


# ==============================================================================
# 3. STAFF ADD API VIEW
# ==============================================================================
class StaffAddAPIView(APIView):
    """
    GET  /api/admin/staff/add/
    POST /api/admin/staff/add/

    Add a new staff member or promote an existing user to staff,
    and grant initial permissions.
    Only superadmins can access this view.
    """
    permission_classes = [IsAuthenticated, IsSuperAdminUser]

    def get(self, request):
        non_staff_users = User.objects.filter(is_staff=False).order_by("username")
        permissions = get_store_permissions()

        return Response({
            "success": True,
            "non_staff_users": NonStaffUserSerializer(non_staff_users, many=True).data,
            "available_permissions": PermissionSerializer(permissions, many=True).data,
        }, status=status.HTTP_200_OK)

    def post(self, request):
        action_type = request.data.get("action_type", "existing")
        selected_perm_ids = _extract_permission_ids(request)

        payload = dict(request.data)
        # Unwrap single-element lists if request.data is a QueryDict
        if hasattr(request.data, "dict"):
            payload = request.data.dict()
        payload["permissions"] = selected_perm_ids
        payload["action_type"] = action_type

        serializer = StaffAddSerializer(data=payload)
        if not serializer.is_valid():
            return Response({
                "success": False,
                "message": "Validation failed.",
                "errors": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        validated_data = serializer.validated_data

        if action_type == "existing":
            user_id = validated_data.get("user_id")
            user = get_object_or_404(User, id=user_id)
            user.is_staff = True
            user.save(update_fields=["is_staff"])
            user.user_permissions.set(selected_perm_ids)

            return Response({
                "success": True,
                "message": f"User '{user.username}' is now a staff member with {len(selected_perm_ids)} permissions.",
                "staff_user": StaffUserSerializer(user).data
            }, status=status.HTTP_200_OK)

        elif action_type == "new":
            username = validated_data.get("username").strip()
            email = validated_data.get("email").strip().lower()
            password = validated_data.get("password")

            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                is_staff=True
            )

            # Auto-activate staff user if custom user flags exist
            if hasattr(user, "is_activated"):
                user.is_activated = True
            if hasattr(user, "is_email_verified"):
                user.is_email_verified = True
            user.save()

            user.user_permissions.set(selected_perm_ids)

            return Response({
                "success": True,
                "message": f"Staff member '{user.username}' created successfully with {len(selected_perm_ids)} permissions.",
                "staff_user": StaffUserSerializer(user).data
            }, status=status.HTTP_201_CREATED)

        return Response({
            "success": False,
            "message": f"Invalid action_type '{action_type}'. Must be 'existing' or 'new'."
        }, status=status.HTTP_400_BAD_REQUEST)


# ==============================================================================
# 4. STAFF REMOVE API VIEW
# ==============================================================================
class StaffRemoveAPIView(APIView):
    """
    POST   /api/admin/staff/<user_id>/remove/
    DELETE /api/admin/staff/<user_id>/remove/

    Revoke staff status and permissions from a staff user.
    Only superadmins can access this view.
    Superadmin accounts cannot be demoted.
    """
    permission_classes = [IsAuthenticated, IsSuperAdminUser]

    def post(self, request, user_id):
        return self._revoke_staff(request, user_id)

    def delete(self, request, user_id):
        return self._revoke_staff(request, user_id)

    def _revoke_staff(self, request, user_id):
        staff_user = get_object_or_404(User, id=user_id, is_staff=True)

        if staff_user.is_superuser:
            return Response({
                "success": False,
                "message": "Superadmin accounts cannot be demoted."
            }, status=status.HTTP_400_BAD_REQUEST)

        staff_user.is_staff = False
        staff_user.user_permissions.clear()
        staff_user.save(update_fields=["is_staff"])

        return Response({
            "success": True,
            "message": f"Staff access revoked for '{staff_user.username}'."
        }, status=status.HTTP_200_OK)


# ==============================================================================
# 5. AVAILABLE PERMISSIONS API VIEW
# ==============================================================================
class AvailablePermissionsAPIView(APIView):
    """
    GET /api/admin/permissions/

    List all assignable permissions across store apps:
    products, coupons, order, chat, accounts.
    Returns both a flat list and a grouped structure by app.
    Only superadmins can access this view.
    """
    permission_classes = [IsAuthenticated, IsSuperAdminUser]

    def get(self, request):
        permissions = get_store_permissions()
        serialized = PermissionSerializer(permissions, many=True).data

        # Group by app_label for frontend presentation
        grouped = {}
        for perm in serialized:
            app = perm["app_label"]
            if app not in grouped:
                grouped[app] = []
            grouped[app].append(perm)

        return Response({
            "success": True,
            "count": len(serialized),
            "store_apps": STORE_APPS,
            "permissions": serialized,
            "grouped_permissions": grouped,
        }, status=status.HTTP_200_OK)


# ==============================================================================
# 6. NON-STAFF CANDIDATES API VIEW
# ==============================================================================
class NonStaffCandidatesAPIView(APIView):
    """
    GET /api/admin/staff/candidates/

    List all non-staff users eligible for promotion to staff.
    Only superadmins can access this view.
    """
    permission_classes = [IsAuthenticated, IsSuperAdminUser]

    def get(self, request):
        non_staff_users = User.objects.filter(is_staff=False).order_by("username")
        serializer = NonStaffUserSerializer(non_staff_users, many=True)
        return Response({
            "success": True,
            "count": non_staff_users.count(),
            "candidates": serializer.data
        }, status=status.HTTP_200_OK)



# ==============================================================================
# 7. USER MANAGEMENT CRUD API VIEWS
# ==============================================================================
class UserListAPI(APIView):
    """
    GET  /api/admin/users/ -> List all users with search and filtering
    POST /api/admin/users/ -> Create a new user (customer, staff, or superadmin)
    """
    permission_classes = [IsAuthenticated, IsSuperAdminUser]

    def get(self, request):
        users = User.objects.all().order_by("-date_joined")

        search = request.GET.get("search", "").strip()
        role = request.GET.get("role", "").strip()
        is_active = request.GET.get("is_active", "").strip().lower()

        if search:
            users = users.filter(
                Q(username__icontains=search)
                | Q(email__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
            )

        if role == "superuser":
            users = users.filter(is_superuser=True)
        elif role == "staff":
            users = users.filter(is_staff=True, is_superuser=False)
        elif role == "customer":
            users = users.filter(is_staff=False)

        if is_active in ("true", "1"):
            users = users.filter(is_active=True)
        elif is_active in ("false", "0"):
            users = users.filter(is_active=False)

        serializer = AdminUserSerializer(users, many=True)
        return Response({
            "success": True,
            "count": users.count(),
            "users": serializer.data
        }, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = AdminUserCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                "success": False,
                "message": "Validation failed.",
                "errors": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        user = serializer.save()
        return Response({
            "success": True,
            "message": f"User '{user.username}' created successfully.",
            "user": AdminUserSerializer(user).data
        }, status=status.HTTP_201_CREATED)


class UserDetailAPI(APIView):
    """
    GET    /api/admin/users/<user_id>/ -> Retrieve user details
    PUT    /api/admin/users/<user_id>/ -> Update user details (full)
    PATCH  /api/admin/users/<user_id>/ -> Update user details (partial)
    DELETE /api/admin/users/<user_id>/ -> Delete user
    """
    permission_classes = [IsAuthenticated, IsSuperAdminUser]

    def get(self, request, user_id):
        user = get_object_or_404(User, id=user_id)
        serializer = AdminUserSerializer(user)
        return Response({
            "success": True,
            "user": serializer.data
        }, status=status.HTTP_200_OK)

    def put(self, request, user_id):
        return self._update(request, user_id, partial=False)

    def patch(self, request, user_id):
        return self._update(request, user_id, partial=True)

    def _update(self, request, user_id, partial=False):
        user = get_object_or_404(User, id=user_id)

        # Safeguard: cannot remove own superuser status or deactivate self
        if request.user.id == user.id:
            if "is_superuser" in request.data and not request.data.get("is_superuser"):
                return Response({
                    "success": False,
                    "message": "You cannot remove your own superuser status."
                }, status=status.HTTP_400_BAD_REQUEST)
            if "is_active" in request.data and not request.data.get("is_active"):
                return Response({
                    "success": False,
                    "message": "You cannot deactivate your own account."
                }, status=status.HTTP_400_BAD_REQUEST)

        serializer = AdminUserUpdateSerializer(user, data=request.data, partial=partial)
        if not serializer.is_valid():
            return Response({
                "success": False,
                "message": "Validation failed.",
                "errors": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        updated_user = serializer.save()
        return Response({
            "success": True,
            "message": f"User '{updated_user.username}' updated successfully.",
            "user": AdminUserSerializer(updated_user).data
        }, status=status.HTTP_200_OK)

    def delete(self, request, user_id):
        user = get_object_or_404(User, id=user_id)

        # Safeguard: cannot delete self
        if request.user.id == user.id:
            return Response({
                "success": False,
                "message": "You cannot delete your own account."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Safeguard: cannot delete superadmin unless superuser
        if user.is_superuser and not request.user.is_superuser:
            return Response({
                "success": False,
                "message": "Superadmin accounts can only be deleted by superadmins."
            }, status=status.HTTP_403_FORBIDDEN)

        username = user.username
        user.delete()
        return Response({
            "success": True,
            "message": f"User '{username}' deleted successfully."
        }, status=status.HTTP_200_OK)


        