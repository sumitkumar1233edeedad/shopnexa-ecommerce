from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages


def staff_perm_required(perm_name):
    """
    Decorator for custom admin panel views.
    Ensures user is logged in, is a staff member, and either is a superuser
    or possesses the specific permission.
    Example: @staff_perm_required('products.add_product')
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect(f"/login/?next={request.path}")

            if not request.user.is_staff:
                messages.error(request, "Access denied. Staff access required.")
                return redirect("home")

            # Superusers always bypass permission checks
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)

            # Check specific Django permission
            if request.user.has_perm(perm_name):
                return view_func(request, *args, **kwargs)

            messages.error(
                request,
                "Access Denied: You do not have permission to perform this action."
            )
            return redirect("admin_dashboard")

        return _wrapped
    return decorator
