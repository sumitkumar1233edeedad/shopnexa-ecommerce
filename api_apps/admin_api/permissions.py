from rest_framework.permissions import BasePermission


class IsSuperAdminUser(BasePermission):
    """
    Permission class that grants access only to authenticated superuser accounts.
    Matches the business rule:
    'Only superadmins can manage staff permissions.'
    """
    message = "Access denied. Only superadmins can manage staff permissions."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_superuser
        )


class IsStaffOrSuperAdminUser(BasePermission):
    """
    Permission class that grants access to any authenticated staff user or superadmin.
    """
    message = "Access denied. Staff or superadmin access required."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.is_staff or request.user.is_superuser)
        )
