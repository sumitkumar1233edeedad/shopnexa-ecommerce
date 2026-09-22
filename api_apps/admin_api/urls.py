from django.urls import path

from .views import (
    AvailablePermissionsAPIView,
    NonStaffCandidatesAPIView,
    StaffAddAPIView,
    StaffListAPIView,
    StaffPermissionsAPIView,
    StaffRemoveAPIView,
)

urlpatterns = [
    # 1. Staff list
    path("admin/staff/", StaffListAPIView.as_view(), name="api_admin_staff_list"),
    path("staff/", StaffListAPIView.as_view(), name="api_staff_list"),

    # 2. Staff add / promote
    path("admin/staff/add/", StaffAddAPIView.as_view(), name="api_admin_staff_add"),
    path("staff/add/", StaffAddAPIView.as_view(), name="api_staff_add"),

    # 3. Staff candidates (non-staff users list)
    path("admin/staff/candidates/", NonStaffCandidatesAPIView.as_view(), name="api_admin_staff_candidates"),
    path("staff/candidates/", NonStaffCandidatesAPIView.as_view(), name="api_staff_candidates"),

    # 4. Staff permissions manage
    path("admin/staff/<int:user_id>/permissions/", StaffPermissionsAPIView.as_view(), name="api_admin_staff_permissions"),
    path("staff/<int:user_id>/permissions/", StaffPermissionsAPIView.as_view(), name="api_staff_permissions"),

    # 5. Staff remove / revoke
    path("admin/staff/<int:user_id>/remove/", StaffRemoveAPIView.as_view(), name="api_admin_staff_remove"),
    path("staff/<int:user_id>/remove/", StaffRemoveAPIView.as_view(), name="api_staff_remove"),

    # 6. Available store permissions catalog
    path("admin/permissions/", AvailablePermissionsAPIView.as_view(), name="api_admin_permissions"),
    path("permissions/", AvailablePermissionsAPIView.as_view(), name="api_permissions"),
]
