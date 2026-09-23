from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()


class AdminApiStaffPermissionTests(APITestCase):
    def setUp(self):
        # 1. Superuser
        self.superadmin = User.objects.create_superuser(
            username="superadmin_tester",
            email="superadmin@example.com",
            password="superpassword123"
        )

        # 2. Staff user
        self.staff_user = User.objects.create_user(
            username="staff_member_one",
            email="staff1@example.com",
            password="staffpassword123",
            is_staff=True
        )

        # 3. Regular non-staff user
        self.regular_user = User.objects.create_user(
            username="regular_customer",
            email="regular@example.com",
            password="regularpassword123",
            is_staff=False
        )

        # Fetch some store permissions for testing
        store_apps = ["products", "coupons", "order", "chat", "accounts"]
        self.sample_perms = list(
            Permission.objects
            .filter(content_type__app_label__in=store_apps)[:3]
        )
        self.sample_perm_ids = [p.id for p in self.sample_perms]

    # =========================================================================
    # PERMISSION & AUTHENTICATION ENFORCEMENT
    # =========================================================================
    def test_anonymous_user_blocked(self):
        """Anonymous requests must be rejected with 401 Unauthorized."""
        url = reverse("api_admin_staff_list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_regular_user_blocked(self):
        """Non-staff / non-superuser requests must be rejected with 403 Forbidden."""
        self.client.force_authenticate(user=self.regular_user)
        url = reverse("api_admin_staff_list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("Only superadmins can manage staff permissions", str(response.data))

    def test_staff_user_not_superuser_blocked(self):
        """Regular staff users without superuser rights must be rejected with 403 Forbidden."""
        self.client.force_authenticate(user=self.staff_user)
        url = reverse("api_admin_staff_list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # =========================================================================
    # STAFF LIST VIEW
    # =========================================================================
    def test_superuser_can_list_staff(self):
        """Superadmin can view staff list with active permissions."""
        self.client.force_authenticate(user=self.superadmin)
        url = reverse("api_admin_staff_list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        usernames = [u["username"] for u in response.data["staff_members"]]
        self.assertIn("superadmin_tester", usernames)
        self.assertIn("staff_member_one", usernames)
        self.assertNotIn("regular_customer", usernames)

    # =========================================================================
    # STAFF PERMISSIONS VIEW (GET & POST)
    # =========================================================================
    def test_get_staff_permissions(self):
        """Superadmin can view assigned and available permissions for a staff user."""
        self.client.force_authenticate(user=self.superadmin)
        if self.sample_perm_ids:
            self.staff_user.user_permissions.set(self.sample_perm_ids[:1])

        url = reverse("api_admin_staff_permissions", kwargs={"user_id": self.staff_user.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["staff_user"]["id"], self.staff_user.id)
        self.assertIn("available_permissions", response.data)
        self.assertIn("user_perm_ids", response.data)

    def test_update_staff_permissions(self):
        """Superadmin can assign/update permissions for a staff member."""
        self.client.force_authenticate(user=self.superadmin)
        url = reverse("api_admin_staff_permissions", kwargs={"user_id": self.staff_user.id})

        payload = {"permissions": self.sample_perm_ids}
        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.staff_user.refresh_from_db()
        current_ids = set(self.staff_user.user_permissions.values_list("id", flat=True))
        self.assertEqual(current_ids, set(self.sample_perm_ids))

    # =========================================================================
    # STAFF ADD VIEW (EXISTING & NEW)
    # =========================================================================
    def test_staff_add_get_options(self):
        """GET /api/admin/staff/add/ returns non-staff candidates and store permissions."""
        self.client.force_authenticate(user=self.superadmin)
        url = reverse("api_admin_staff_add")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertIn("non_staff_users", response.data)
        self.assertIn("available_permissions", response.data)

    def test_promote_existing_user_to_staff(self):
        """Superadmin can promote an existing customer to staff and grant permissions."""
        self.client.force_authenticate(user=self.superadmin)
        url = reverse("api_admin_staff_add")

        payload = {
            "action_type": "existing",
            "user_id": self.regular_user.id,
            "permissions": self.sample_perm_ids
        }
        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.regular_user.refresh_from_db()
        self.assertTrue(self.regular_user.is_staff)
        current_ids = set(self.regular_user.user_permissions.values_list("id", flat=True))
        self.assertEqual(current_ids, set(self.sample_perm_ids))

    def test_create_new_staff_member(self):
        """Superadmin can create a brand new staff user with credentials and permissions."""
        self.client.force_authenticate(user=self.superadmin)
        url = reverse("api_admin_staff_add")

        payload = {
            "action_type": "new",
            "username": "brand_new_staff",
            "email": "brandnew@example.com",
            "password": "SecurePassword123!",
            "permissions": self.sample_perm_ids
        }
        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["success"])

        new_user = User.objects.get(username="brand_new_staff")
        self.assertTrue(new_user.is_staff)
        self.assertEqual(new_user.email, "brandnew@example.com")
        current_ids = set(new_user.user_permissions.values_list("id", flat=True))
        self.assertEqual(current_ids, set(self.sample_perm_ids))

    def test_create_new_staff_duplicate_username_rejected(self):
        """Attempting to create staff with an existing username returns 400 Bad Request."""
        self.client.force_authenticate(user=self.superadmin)
        url = reverse("api_admin_staff_add")

        payload = {
            "action_type": "new",
            "username": self.staff_user.username,
            "email": "different_email@example.com",
            "password": "SecurePassword123!",
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # =========================================================================
    # STAFF REMOVE VIEW
    # =========================================================================
    def test_cannot_demote_superadmin(self):
        """Superadmin account cannot be demoted or removed."""
        self.client.force_authenticate(user=self.superadmin)
        url = reverse("api_admin_staff_remove", kwargs={"user_id": self.superadmin.id})

        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Superadmin accounts cannot be demoted", response.data["message"])

    def test_revoke_staff_access(self):
        """Superadmin can revoke staff status and clear permissions from a staff user."""
        self.client.force_authenticate(user=self.superadmin)
        if self.sample_perm_ids:
            self.staff_user.user_permissions.set(self.sample_perm_ids)

        url = reverse("api_admin_staff_remove", kwargs={"user_id": self.staff_user.id})
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])

        self.staff_user.refresh_from_db()
        self.assertFalse(self.staff_user.is_staff)
        self.assertEqual(self.staff_user.user_permissions.count(), 0)

    # =========================================================================
    # CATALOG ENDPOINTS
    # =========================================================================
    def test_available_permissions_endpoint(self):
        """GET /api/admin/permissions/ returns permissions grouped by app."""
        self.client.force_authenticate(user=self.superadmin)
        url = reverse("api_admin_permissions")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertIn("permissions", response.data)
        self.assertIn("grouped_permissions", response.data)
        self.assertIn("store_apps", response.data)

    # =========================================================================
    # USER MANAGEMENT CRUD ENDPOINTS
    # =========================================================================
    def test_list_users_as_superuser(self):
        """Superadmin can list all users with metadata."""
        self.client.force_authenticate(user=self.superadmin)
        url = reverse("api_admin_user_list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertGreaterEqual(response.data["count"], 3)
        usernames = [u["username"] for u in response.data["users"]]
        self.assertIn(self.superadmin.username, usernames)
        self.assertIn(self.staff_user.username, usernames)
        self.assertIn(self.regular_user.username, usernames)

    def test_list_users_search_filter(self):
        """Users list can be filtered by search query."""
        self.client.force_authenticate(user=self.superadmin)
        url = reverse("api_admin_user_list")
        response = self.client.get(url, {"search": "regular"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        usernames = [u["username"] for u in response.data["users"]]
        self.assertIn("regular_customer", usernames)
        self.assertNotIn("superadmin_tester", usernames)

    def test_create_user_api(self):
        """Superadmin can create a new user via API."""
        self.client.force_authenticate(user=self.superadmin)
        url = reverse("api_admin_user_list")
        payload = {
            "username": "new_created_user",
            "email": "newuser@example.com",
            "password": "strongpassword123",
            "first_name": "Test",
            "last_name": "User",
            "is_active": True,
        }
        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["user"]["username"], "new_created_user")
        self.assertTrue(User.objects.filter(username="new_created_user").exists())

    def test_retrieve_user_api(self):
        """Superadmin can retrieve single user details."""
        self.client.force_authenticate(user=self.superadmin)
        url = reverse("api_admin_user_detail", kwargs={"user_id": self.regular_user.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["user"]["id"], self.regular_user.id)
        self.assertEqual(response.data["user"]["username"], self.regular_user.username)

    def test_update_user_api(self):
        """Superadmin can update user fields."""
        self.client.force_authenticate(user=self.superadmin)
        url = reverse("api_admin_user_detail", kwargs={"user_id": self.regular_user.id})
        payload = {
            "first_name": "UpdatedName",
            "last_name": "UpdatedLastName",
        }
        response = self.client.patch(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["user"]["first_name"], "UpdatedName")
        self.regular_user.refresh_from_db()
        self.assertEqual(self.regular_user.first_name, "UpdatedName")

    def test_delete_user_api(self):
        """Superadmin can delete a user."""
        target_user = User.objects.create_user(
            username="to_be_deleted",
            email="delete_me@example.com",
            password="testpassword123"
        )
        self.client.force_authenticate(user=self.superadmin)
        url = reverse("api_admin_user_detail", kwargs={"user_id": target_user.id})
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertFalse(User.objects.filter(username="to_be_deleted").exists())

    def test_cannot_delete_self_api(self):
        """Superadmin cannot delete their own account."""
        self.client.force_authenticate(user=self.superadmin)
        url = reverse("api_admin_user_detail", kwargs={"user_id": self.superadmin.id})
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("cannot delete your own account", response.data["message"])
        self.assertTrue(User.objects.filter(id=self.superadmin.id).exists())

