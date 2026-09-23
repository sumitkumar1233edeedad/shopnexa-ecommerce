from datetime import timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.coupons.models import Coupon, CouponUsage
from apps.order.models import Order
from apps.payment.models import Payment

User = get_user_model()


class AdminCouponManagementTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Admin user
        self.admin_user = User.objects.create_user(
            username="adminuser",
            email="admin@example.com",
            password="adminpassword123",
            is_staff=True,
            is_superuser=True,
        )

        # Normal customer user
        self.customer = User.objects.create_user(
            username="customer1",
            email="customer1@example.com",
            password="customerpassword123",
            is_staff=False,
        )

        # Initial test coupon
        now = timezone.now()
        self.coupon = Coupon.objects.create(
            code="WELCOME20",
            description="20% off welcome coupon",
            discount_type="percentage",
            discount_value=Decimal("20.00"),
            minimum_order_amount=Decimal("500.00"),
            maximum_discount_amount=Decimal("300.00"),
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=30),
            usage_limit=100,
            per_user_limit=2,
            weekly_user_limit=5,
            is_active=True,
        )

    def test_unauthenticated_user_redirected_to_admin_login(self):
        response = self.client.get(reverse("admin_coupons"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_non_staff_user_redirected_to_home(self):
        self.client.login(username="customer1", password="customerpassword123")
        response = self.client.get(reverse("admin_coupons"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("home"))

    def test_admin_can_view_coupon_list(self):
        self.client.login(username="adminuser", password="adminpassword123")
        response = self.client.get(reverse("admin_coupons"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "adminpanel/admin_coupon_list.html")
        self.assertContains(response, "WELCOME20")
        self.assertContains(response, "20%")
        self.assertContains(response, "+ Add Coupon")

    def test_admin_can_search_and_filter_coupons(self):
        self.client.login(username="adminuser", password="adminpassword123")

        now = timezone.now()
        Coupon.objects.create(
            code="FLAT100",
            discount_type="fixed",
            discount_value=Decimal("100.00"),
            valid_from=now,
            valid_until=now + timedelta(days=10),
            is_active=False,
        )

        # Search
        response = self.client.get(reverse("admin_coupons"), {"search": "FLAT"})
        self.assertContains(response, "FLAT100")
        self.assertNotContains(response, "WELCOME20")

        # Filter by status: inactive
        response = self.client.get(reverse("admin_coupons"), {"status": "inactive"})
        self.assertContains(response, "FLAT100")
        self.assertNotContains(response, "WELCOME20")

        # Filter by discount_type: percentage
        response = self.client.get(reverse("admin_coupons"), {"discount_type": "percentage"})
        self.assertContains(response, "WELCOME20")
        self.assertNotContains(response, "FLAT100")

    def test_admin_can_create_coupon_with_weekly_user_limit(self):
        self.client.login(username="adminuser", password="adminpassword123")

        now = timezone.now()
        post_data = {
            "code": "SUPERDEAL",
            "description": "Super weekly deal",
            "discount_type": "percentage",
            "discount_value": "25.00",
            "minimum_order_amount": "1000.00",
            "maximum_discount_amount": "500.00",
            "weekly_user_limit": "3",
            "usage_limit": "50",
            "per_user_limit": "2",
            "valid_from": now.strftime("%Y-%m-%dT%H:%M"),
            "valid_until": (now + timedelta(days=15)).strftime("%Y-%m-%dT%H:%M"),
            "is_active": "on",
        }

        response = self.client.post(reverse("admin_coupon_add"), post_data, follow=True)
        self.assertEqual(response.status_code, 200)

        created = Coupon.objects.filter(code="SUPERDEAL").first()
        self.assertIsNotNone(created)
        self.assertEqual(created.weekly_user_limit, 3)
        self.assertEqual(created.discount_value, Decimal("25.00"))
        self.assertEqual(created.minimum_order_amount, Decimal("1000.00"))
        self.assertTrue(created.is_active)

    def test_admin_add_coupon_validations(self):
        self.client.login(username="adminuser", password="adminpassword123")

        # Duplicate code
        now = timezone.now()
        post_data = {
            "code": "WELCOME20",
            "discount_type": "percentage",
            "discount_value": "10.00",
            "valid_from": now.strftime("%Y-%m-%dT%H:%M"),
            "valid_until": (now + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M"),
        }
        response = self.client.post(reverse("admin_coupon_add"), post_data)
        self.assertContains(response, "already exists")

        # Invalid dates (until before from)
        post_data["code"] = "NEWCODE"
        post_data["valid_until"] = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        response = self.client.post(reverse("admin_coupon_add"), post_data)
        self.assertContains(response, "must be after valid from date")

    def test_admin_can_edit_coupon(self):
        self.client.login(username="adminuser", password="adminpassword123")

        now = timezone.now()
        post_data = {
            "code": "WELCOME20_EDITED",
            "description": "Updated description",
            "discount_type": "fixed",
            "discount_value": "150.00",
            "minimum_order_amount": "800.00",
            "maximum_discount_amount": "",
            "weekly_user_limit": "7",
            "usage_limit": "200",
            "per_user_limit": "3",
            "valid_from": now.strftime("%Y-%m-%dT%H:%M"),
            "valid_until": (now + timedelta(days=60)).strftime("%Y-%m-%dT%H:%M"),
            "is_active": "on",
        }

        response = self.client.post(
            reverse("admin_coupon_edit", kwargs={"slug": self.coupon.slug}),
            post_data,
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        self.coupon.refresh_from_db()
        self.assertEqual(self.coupon.code, "WELCOME20_EDITED")
        self.assertEqual(self.coupon.discount_type, "fixed")
        self.assertEqual(self.coupon.discount_value, Decimal("150.00"))
        self.assertEqual(self.coupon.weekly_user_limit, 7)

    def test_admin_can_toggle_coupon_active_status(self):
        self.client.login(username="adminuser", password="adminpassword123")
        self.assertTrue(self.coupon.is_active)

        response = self.client.get(
            reverse("admin_coupon_toggle", kwargs={"slug": self.coupon.slug}),
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.coupon.refresh_from_db()
        self.assertFalse(self.coupon.is_active)

        # Toggle back
        response = self.client.get(
            reverse("admin_coupon_toggle", kwargs={"slug": self.coupon.slug}),
            follow=True,
        )
        self.coupon.refresh_from_db()
        self.assertTrue(self.coupon.is_active)

    def test_admin_can_view_coupon_detail_with_usages(self):
        self.client.login(username="adminuser", password="adminpassword123")

        order = Order.objects.create(
            user=self.customer,
            order_number="ORD-TEST-001",
            status="confirmed",
            total_amount=Decimal("800.00"),
            coupon=self.coupon,
            discount_amount=Decimal("160.00"),
            shipping_name="Customer One",
            shipping_phone="9876543210",
            shipping_city="Mumbai",
            shipping_pincode="400001",
            shipping_address="123 Test Street",
        )
        Payment.objects.create(
            order=order,
            user=self.customer,
            payment_method="card",
            transaction_id="TXN-TEST-001",
            amount=Decimal("800.00"),
            status="completed",
            paid_at=timezone.now(),
        )

        response = self.client.get(reverse("admin_coupon_detail", kwargs={"slug": self.coupon.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "adminpanel/admin_coupon_detail.html")
        self.assertContains(response, "WELCOME20")
        self.assertContains(response, "customer1")
        self.assertContains(response, "ORD-TEST-001")
        self.assertContains(response, "160.00")

    def test_admin_delete_coupon_without_usages_hard_deletes(self):
        self.client.login(username="adminuser", password="adminpassword123")

        now = timezone.now()
        new_coupon = Coupon.objects.create(
            code="UNUSED10",
            discount_type="fixed",
            discount_value=Decimal("10.00"),
            valid_from=now,
            valid_until=now + timedelta(days=5),
        )
        slug = new_coupon.slug

        response = self.client.post(
            reverse("admin_coupon_delete", kwargs={"slug": slug}),
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Coupon.objects.filter(slug=slug).exists())

    def test_admin_delete_coupon_with_usages_soft_deactivates(self):
        self.client.login(username="adminuser", password="adminpassword123")

        order = Order.objects.create(
            user=self.customer,
            order_number="ORD-TEST-002",
            status="confirmed",
            total_amount=Decimal("900.00"),
            coupon=self.coupon,
            discount_amount=Decimal("180.00"),
            shipping_name="Customer One",
            shipping_phone="9876543210",
            shipping_city="Mumbai",
            shipping_pincode="400001",
            shipping_address="123 Test Street",
        )
        CouponUsage.objects.create(
            coupon=self.coupon,
            user=self.customer,
            order=order,
            discount_amount=Decimal("180.00"),
        )

        slug = self.coupon.slug
        response = self.client.post(
            reverse("admin_coupon_delete", kwargs={"slug": slug}),
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        # Still exists in DB to protect order records, but is deactivated
        self.coupon.refresh_from_db()
        self.assertTrue(Coupon.objects.filter(slug=slug).exists())
        self.assertFalse(self.coupon.is_active)
        self.assertContains(response, "has historical order usage records and cannot be permanently deleted")


class AdminUserListTests(TestCase):
    def setUp(self):
        self.client = Client()

        self.superuser = User.objects.create_superuser(
            username="admin_super",
            email="super@example.com",
            password="superpassword123",
        )

        self.staff_user = User.objects.create_user(
            username="staff_member",
            email="staff@example.com",
            password="staffpassword123",
            is_staff=True,
        )

        self.regular_user = User.objects.create_user(
            username="regular_cust",
            email="cust@example.com",
            password="custpassword123",
            is_staff=False,
        )

    def test_anonymous_redirected(self):
        response = self.client.get(reverse("admin_users"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_non_staff_redirected_to_home(self):
        self.client.login(username="regular_cust", password="custpassword123")
        response = self.client.get(reverse("admin_users"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("home"))

    def test_superuser_can_access_user_list(self):
        self.client.login(username="admin_super", password="superpassword123")
        response = self.client.get(reverse("admin_users"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "adminpanel/admin_user_list.html")
        self.assertContains(response, "User Management")
        self.assertContains(response, "admin_super")
        self.assertContains(response, "regular_cust")

