from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model

User = get_user_model()
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.order.models import Order
from apps.payment.models import Payment
from apps.coupons.models import Coupon, CouponConfiguration, CouponUsage
from apps.coupons.services import (
    can_user_use_coupon,
    get_current_week_bounds,
    get_user_weekly_coupon_info,
    get_user_weekly_coupon_usage,
    record_coupon_usage,
    validate_coupon_for_user,
)


class CouponSystemTests(TestCase):

    def setUp(self):
        # Create test users
        self.user = User.objects.create_user(
            username="testuser",
            email="testuser@example.com",
            password="password123"
        )
        self.other_user = User.objects.create_user(
            username="otheruser",
            email="otheruser@example.com",
            password="password123"
        )

        # Base configuration: default limit 5
        self.config = CouponConfiguration.get_config()
        self.config.weekly_user_limit = 5
        self.config.save()

        now = timezone.now()

        # Standard percentage coupon
        self.coupon_pct = Coupon.objects.create(
            code="SAVE20",
            description="20% off up to ₹500 on min ₹1000",
            discount_type="percentage",
            discount_value=Decimal("20.00"),
            minimum_order_amount=Decimal("1000.00"),
            maximum_discount_amount=Decimal("500.00"),
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=10),
            usage_limit=1000,
            used_count=0,
            per_user_limit=5,
            is_active=True,
        )

        # Standard fixed coupon
        self.coupon_fixed = Coupon.objects.create(
            code="FLAT200",
            description="Flat ₹200 off on min ₹500",
            discount_type="fixed",
            discount_value=Decimal("200.00"),
            minimum_order_amount=Decimal("500.00"),
            maximum_discount_amount=None,
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=10),
            usage_limit=1000,
            used_count=0,
            per_user_limit=5,
            is_active=True,
        )

    def _create_completed_order(self, user, order_num, amount, coupon=None, discount=Decimal("0.00")):
        order = Order.objects.create(
            user=user,
            order_number=order_num,
            status="confirmed",
            total_amount=amount,
            coupon=coupon,
            discount_amount=discount,
            shipping_name="Test Recipient",
            shipping_phone="9876543210",
            shipping_city="Mumbai",
            shipping_pincode="400001",
            shipping_address="123 Test Street, Mumbai",
        )
        payment = Payment.objects.create(
            user=user,
            order=order,
            payment_method="card",
            transaction_id=f"TXN-{order_num}",
            amount=amount,
            status="completed",
            paid_at=timezone.now(),
        )
        return order, payment

    def _create_failed_order(self, user, order_num, amount, coupon=None):
        order = Order.objects.create(
            user=user,
            order_number=order_num,
            status="pending",
            total_amount=amount,
            coupon=coupon,
            discount_amount=Decimal("0.00"),
            shipping_name="Test Recipient",
            shipping_phone="9876543210",
            shipping_city="Mumbai",
            shipping_pincode="400001",
            shipping_address="123 Test Street, Mumbai",
        )
        payment = Payment.objects.create(
            user=user,
            order=order,
            payment_method="card",
            transaction_id=f"TXN-FAIL-{order_num}",
            amount=amount,
            status="failed",
            paid_at=None,
        )
        return order, payment

    # -------------------------------------------------------------------------
    # TEST 1: User can use coupon when weekly usage is 0
    # -------------------------------------------------------------------------
    def test_01_user_can_use_coupon_when_weekly_usage_is_0(self):
        self.assertEqual(get_user_weekly_coupon_usage(self.user), 0)
        can_use, msg = can_user_use_coupon(self.user)
        self.assertTrue(can_use)
        self.assertEqual(msg, "")

        is_valid, err, coupon, discount = validate_coupon_for_user(
            "SAVE20", self.user, Decimal("2000.00")
        )
        self.assertTrue(is_valid)
        self.assertEqual(err, "")
        self.assertIsNotNone(coupon)
        self.assertEqual(discount, Decimal("400.00"))

    # -------------------------------------------------------------------------
    # TEST 2: User can use coupon when weekly usage is 4
    # -------------------------------------------------------------------------
    def test_02_user_can_use_coupon_when_weekly_usage_is_4(self):
        now = timezone.now()
        # Seed 4 successful usages for current week
        for i in range(1, 5):
            order, _ = self._create_completed_order(
                self.user, f"ORD-WK4-{i}", Decimal("1000.00"), coupon=None
            )
            CouponUsage.objects.create(
                coupon=self.coupon_pct,
                user=self.user,
                order=order,
                discount_amount=Decimal("200.00"),
                used_at=now
            )

        self.assertEqual(get_user_weekly_coupon_usage(self.user), 4)
        can_use, msg = can_user_use_coupon(self.user)
        self.assertTrue(can_use)
        self.assertEqual(msg, "")

        is_valid, err, coupon, discount = validate_coupon_for_user(
            "FLAT200", self.user, Decimal("1000.00")
        )
        self.assertTrue(is_valid)
        self.assertEqual(err, "")

    # -------------------------------------------------------------------------
    # TEST 3: User cannot use coupon when weekly usage is 5
    # -------------------------------------------------------------------------
    def test_03_user_cannot_use_coupon_when_weekly_usage_is_5(self):
        now = timezone.now()
        for i in range(1, 6):
            order, _ = self._create_completed_order(
                self.user, f"ORD-WK5-{i}", Decimal("1000.00"), coupon=None
            )
            CouponUsage.objects.create(
                coupon=self.coupon_pct,
                user=self.user,
                order=order,
                discount_amount=Decimal("200.00"),
                used_at=now
            )

        self.assertEqual(get_user_weekly_coupon_usage(self.user), 5)
        can_use, msg = can_user_use_coupon(self.user)
        self.assertFalse(can_use)
        self.assertIn("Weekly coupon limit reached", msg)

        is_valid, err, coupon, discount = validate_coupon_for_user(
            "FLAT200", self.user, Decimal("1000.00")
        )
        self.assertFalse(is_valid)
        self.assertIn("You have reached your weekly coupon limit of 5 uses", err)
        self.assertEqual(discount, Decimal("0.00"))

    # -------------------------------------------------------------------------
    # TEST 4: Weekly usage resets when a new week starts
    # -------------------------------------------------------------------------
    def test_04_weekly_usage_resets_when_new_week_starts(self):
        now = timezone.now()
        start_of_current_week, _ = get_current_week_bounds(now)
        # Create 5 usages in the previous week
        previous_week_time = start_of_current_week - timedelta(days=2)

        prev_coupon = Coupon.objects.create(
            code="PREVWK",
            discount_type="fixed",
            discount_value=Decimal("50.00"),
            minimum_order_amount=Decimal("100.00"),
            valid_from=now - timedelta(days=15),
            valid_until=now + timedelta(days=15),
            per_user_limit=10,
            is_active=True
        )

        for i in range(1, 6):
            order, _ = self._create_completed_order(
                self.user, f"ORD-OLD-WK-{i}", Decimal("1000.00"), coupon=None
            )
            CouponUsage.objects.create(
                coupon=prev_coupon,
                user=self.user,
                order=order,
                discount_amount=Decimal("50.00"),
                used_at=previous_week_time
            )

        # Total usages in database = 5, but for current week = 0
        self.assertEqual(CouponUsage.objects.filter(user=self.user).count(), 5)
        self.assertEqual(get_user_weekly_coupon_usage(self.user), 0)

        can_use, _ = can_user_use_coupon(self.user)
        self.assertTrue(can_use)

        is_valid, err, _, _ = validate_coupon_for_user(
            "SAVE20", self.user, Decimal("2000.00")
        )
        self.assertTrue(is_valid, f"Expected valid in new week, but got error: {err}")

    # -------------------------------------------------------------------------
    # TEST 5: Failed payment does not increase weekly usage
    # -------------------------------------------------------------------------
    def test_05_failed_payment_does_not_increase_weekly_usage(self):
        order, payment = self._create_failed_order(
            self.user, "ORD-FAIL-1", Decimal("1500.00"), self.coupon_pct
        )
        usage = record_coupon_usage(order, coupon=self.coupon_pct, discount_amount=Decimal("300.00"))
        self.assertIsNone(usage)
        self.assertEqual(CouponUsage.objects.filter(order=order).count(), 0)
        self.assertEqual(get_user_weekly_coupon_usage(self.user), 0)
        self.coupon_pct.refresh_from_db()
        self.assertEqual(self.coupon_pct.used_count, 0)

    # -------------------------------------------------------------------------
    # TEST 6: Successful payment increases weekly usage
    # -------------------------------------------------------------------------
    def test_06_successful_payment_increases_weekly_usage(self):
        order, payment = self._create_completed_order(
            self.user, "ORD-SUCC-1", Decimal("1600.00"), coupon=None
        )
        self.assertEqual(get_user_weekly_coupon_usage(self.user), 0)

        usage = record_coupon_usage(order, coupon=self.coupon_pct, discount_amount=Decimal("400.00"))
        self.assertIsNotNone(usage)
        self.assertEqual(usage.discount_amount, Decimal("400.00"))
        self.assertEqual(get_user_weekly_coupon_usage(self.user), 1)

        self.coupon_pct.refresh_from_db()
        self.assertEqual(self.coupon_pct.used_count, 1)

    # -------------------------------------------------------------------------
    # TEST 7: Same order cannot create duplicate CouponUsage records
    # -------------------------------------------------------------------------
    def test_07_same_order_cannot_create_duplicate_coupon_usage_records(self):
        order, payment = self._create_completed_order(
            self.user, "ORD-NODUP-1", Decimal("1600.00"), coupon=None
        )
        usage1 = record_coupon_usage(order, coupon=self.coupon_pct, discount_amount=Decimal("400.00"))
        self.assertIsNotNone(usage1)
        self.assertEqual(CouponUsage.objects.filter(order=order).count(), 1)
        self.coupon_pct.refresh_from_db()
        self.assertEqual(self.coupon_pct.used_count, 1)

        # Call again (simulating duplicate webhook / callback)
        usage2 = record_coupon_usage(order, coupon=self.coupon_pct, discount_amount=Decimal("400.00"))
        self.assertEqual(usage1.pk, usage2.pk)
        self.assertEqual(CouponUsage.objects.filter(order=order).count(), 1)
        self.coupon_pct.refresh_from_db()
        self.assertEqual(self.coupon_pct.used_count, 1)  # NOT incremented again!

        # Direct database uniqueness enforcement
        with self.assertRaises(IntegrityError):
            CouponUsage.objects.create(
                coupon=self.coupon_pct,
                user=self.user,
                order=order,
                discount_amount=Decimal("400.00")
            )

    # -------------------------------------------------------------------------
    # TEST 8: Global coupon limit works
    # -------------------------------------------------------------------------
    def test_08_global_coupon_limit_works(self):
        limited_coupon = Coupon.objects.create(
            code="GLOBAL5",
            discount_type="fixed",
            discount_value=Decimal("50.00"),
            minimum_order_amount=Decimal("100.00"),
            valid_from=timezone.now() - timedelta(days=1),
            valid_until=timezone.now() + timedelta(days=5),
            usage_limit=5,
            used_count=5,
            per_user_limit=10,
            is_active=True
        )
        is_valid, err, _, _ = validate_coupon_for_user(
            "GLOBAL5", self.user, Decimal("500.00")
        )
        self.assertFalse(is_valid)
        self.assertEqual(err, "This coupon has reached its usage limit.")

    # -------------------------------------------------------------------------
    # TEST 9: Per-user coupon limit works
    # -------------------------------------------------------------------------
    def test_09_per_user_coupon_limit_works(self):
        per_user_coupon = Coupon.objects.create(
            code="LIMIT2",
            discount_type="fixed",
            discount_value=Decimal("100.00"),
            minimum_order_amount=Decimal("500.00"),
            valid_from=timezone.now() - timedelta(days=1),
            valid_until=timezone.now() + timedelta(days=5),
            usage_limit=1000,
            used_count=2,
            per_user_limit=2,
            is_active=True
        )
        # Create 2 usages for self.user
        for i in range(1, 3):
            order, _ = self._create_completed_order(
                self.user, f"ORD-PERUSER-{i}", Decimal("800.00"), coupon=None
            )
            CouponUsage.objects.create(
                coupon=per_user_coupon,
                user=self.user,
                order=order,
                discount_amount=Decimal("100.00")
            )

        # Third attempt by self.user should be rejected
        is_valid, err, _, _ = validate_coupon_for_user(
            "LIMIT2", self.user, Decimal("800.00")
        )
        self.assertFalse(is_valid)
        self.assertEqual(err, "You have already used this coupon the maximum allowed number of times.")

        # Another user who hasn't reached per-user limit should still be allowed!
        is_valid_other, err_other, _, _ = validate_coupon_for_user(
            "LIMIT2", self.other_user, Decimal("800.00")
        )
        self.assertTrue(is_valid_other)
        self.assertEqual(err_other, "")

    # -------------------------------------------------------------------------
    # TEST 10: Weekly user limit works independently from per-user coupon limit
    # -------------------------------------------------------------------------
    def test_10_weekly_user_limit_works_independently_from_per_user_limit(self):
        # Admin weekly limit is 5.
        # User uses 5 DIFFERENT coupons with per_user_limit=1 each.
        coupons = []
        for i in range(1, 6):
            c = Coupon.objects.create(
                code=f"UNIQUE{i}",
                discount_type="fixed",
                discount_value=Decimal("50.00"),
                minimum_order_amount=Decimal("100.00"),
                valid_from=timezone.now() - timedelta(days=1),
                valid_until=timezone.now() + timedelta(days=5),
                usage_limit=1000,
                used_count=0,
                per_user_limit=1,
                is_active=True
            )
            coupons.append(c)

        # Use all 5 coupons once
        for i, c in enumerate(coupons, start=1):
            order, _ = self._create_completed_order(
                self.user, f"ORD-INDEP-{i}", Decimal("500.00"), coupon=None
            )
            CouponUsage.objects.create(
                coupon=c,
                user=self.user,
                order=order,
                discount_amount=Decimal("50.00"),
                used_at=timezone.now()
            )

        # Now weekly usage = 5
        self.assertEqual(get_user_weekly_coupon_usage(self.user), 5)

        # Try a 6th DIFFERENT coupon where per_user_limit is 1 and user usage for it is 0
        c6 = Coupon.objects.create(
            code="UNIQUE6",
            discount_type="fixed",
            discount_value=Decimal("50.00"),
            minimum_order_amount=Decimal("100.00"),
            valid_from=timezone.now() - timedelta(days=1),
            valid_until=timezone.now() + timedelta(days=5),
            usage_limit=1000,
            used_count=0,
            per_user_limit=1,
            is_active=True
        )

        is_valid, err, _, _ = validate_coupon_for_user("UNIQUE6", self.user, Decimal("500.00"))
        self.assertFalse(is_valid)
        self.assertIn("You have reached your weekly coupon limit of 5 uses", err)

    # -------------------------------------------------------------------------
    # TEST 11: Expired coupon is rejected
    # -------------------------------------------------------------------------
    def test_11_expired_coupon_is_rejected(self):
        expired_coupon = Coupon.objects.create(
            code="EXPIRED10",
            discount_type="fixed",
            discount_value=Decimal("100.00"),
            minimum_order_amount=Decimal("500.00"),
            valid_from=timezone.now() - timedelta(days=10),
            valid_until=timezone.now() - timedelta(days=1),
            is_active=True
        )
        is_valid, err, _, _ = validate_coupon_for_user(
            "EXPIRED10", self.user, Decimal("600.00")
        )
        self.assertFalse(is_valid)
        self.assertEqual(err, "This coupon has expired.")

    # -------------------------------------------------------------------------
    # TEST 12: Inactive coupon is rejected
    # -------------------------------------------------------------------------
    def test_12_inactive_coupon_is_rejected(self):
        inactive_coupon = Coupon.objects.create(
            code="INACTIVE20",
            discount_type="percentage",
            discount_value=Decimal("20.00"),
            minimum_order_amount=Decimal("500.00"),
            valid_from=timezone.now() - timedelta(days=1),
            valid_until=timezone.now() + timedelta(days=10),
            is_active=False
        )
        is_valid, err, _, _ = validate_coupon_for_user(
            "INACTIVE20", self.user, Decimal("600.00")
        )
        self.assertFalse(is_valid)
        self.assertEqual(err, "This coupon is not active.")

    # -------------------------------------------------------------------------
    # TEST 13: Minimum order amount works
    # -------------------------------------------------------------------------
    def test_13_minimum_order_amount_works(self):
        # self.coupon_pct requires min ₹1000
        is_valid, err, _, _ = validate_coupon_for_user(
            "SAVE20", self.user, Decimal("999.99")
        )
        self.assertFalse(is_valid)
        self.assertEqual(err, "Minimum order amount is ₹1,000.")

        # At exactly ₹1000 it is valid
        is_valid_exact, err_exact, _, _ = validate_coupon_for_user(
            "SAVE20", self.user, Decimal("1000.00")
        )
        self.assertTrue(is_valid_exact)

    # -------------------------------------------------------------------------
    # TEST 14: Maximum discount works
    # -------------------------------------------------------------------------
    def test_14_maximum_discount_works(self):
        # 20% on ₹10,000 = ₹2,000, but capped at maximum_discount_amount = ₹500
        is_valid, err, _, discount = validate_coupon_for_user(
            "SAVE20", self.user, Decimal("10000.00")
        )
        self.assertTrue(is_valid)
        self.assertEqual(discount, Decimal("500.00"))

    # -------------------------------------------------------------------------
    # TEST 15: Fixed discount works
    # -------------------------------------------------------------------------
    def test_15_fixed_discount_works(self):
        is_valid, err, _, discount = validate_coupon_for_user(
            "FLAT200", self.user, Decimal("800.00")
        )
        self.assertTrue(is_valid)
        self.assertEqual(discount, Decimal("200.00"))

    # -------------------------------------------------------------------------
    # TEST 16: Percentage discount works
    # -------------------------------------------------------------------------
    def test_16_percentage_discount_works(self):
        # 20% on ₹1500 = ₹300 (under ₹500 cap)
        is_valid, err, _, discount = validate_coupon_for_user(
            "SAVE20", self.user, Decimal("1500.00")
        )
        self.assertTrue(is_valid)
        self.assertEqual(discount, Decimal("300.00"))

    # -------------------------------------------------------------------------
    # TEST 17: Discount cannot make order total negative
    # -------------------------------------------------------------------------
    def test_17_discount_cannot_make_order_total_negative(self):
        huge_discount_coupon = Coupon.objects.create(
            code="BIGDISCOUNT",
            discount_type="fixed",
            discount_value=Decimal("5000.00"),
            minimum_order_amount=Decimal("100.00"),
            valid_from=timezone.now() - timedelta(days=1),
            valid_until=timezone.now() + timedelta(days=5),
            is_active=True
        )
        is_valid, err, _, discount = validate_coupon_for_user(
            "BIGDISCOUNT", self.user, Decimal("500.00")
        )
        self.assertTrue(is_valid)
        # Discount must be capped at order total (₹500), not exceeding it!
        self.assertEqual(discount, Decimal("500.00"))
        total = max(Decimal("0.00"), Decimal("500.00") - discount)
        self.assertEqual(total, Decimal("0.00"))

    # -------------------------------------------------------------------------
    # TEST 18: Case-insensitive coupon codes work
    # -------------------------------------------------------------------------
    def test_18_case_insensitive_coupon_codes_work(self):
        for variant in ["save20", "SaVe20", "SAVE20", "   save20   "]:
            is_valid, err, coupon, discount = validate_coupon_for_user(
                variant, self.user, Decimal("2000.00")
            )
            self.assertTrue(is_valid, f"Failed for variant: {variant}")
            self.assertEqual(coupon.code, "SAVE20")
            self.assertEqual(discount, Decimal("400.00"))

    # -------------------------------------------------------------------------
    # TEST 19: Anonymous users cannot use coupons
    # -------------------------------------------------------------------------
    def test_19_anonymous_users_cannot_use_coupons(self):
        from django.contrib.auth.models import AnonymousUser
        anon = AnonymousUser()

        can_use, msg = can_user_use_coupon(anon)
        self.assertFalse(can_use)
        self.assertEqual(msg, "Please log in to use coupons.")

        is_valid, err, _, _ = validate_coupon_for_user("SAVE20", anon, Decimal("2000.00"))
        self.assertFalse(is_valid)
        self.assertEqual(err, "Please log in to use coupons.")

    # -------------------------------------------------------------------------
    # TEST 20: Admin can change the weekly limit from 5 to another value
    # -------------------------------------------------------------------------
    def test_20_admin_can_change_weekly_limit(self):
        # Default is 5
        self.assertEqual(CouponConfiguration.get_weekly_limit(), 5)

        # Seed 5 usages for self.user
        now = timezone.now()
        for i in range(1, 6):
            order, _ = self._create_completed_order(
                self.user, f"ORD-ADMIN-CFG-{i}", Decimal("1000.00"), coupon=None
            )
            CouponUsage.objects.create(
                coupon=self.coupon_pct,
                user=self.user,
                order=order,
                discount_amount=Decimal("200.00"),
                used_at=now
            )

        # At limit of 5, user is rejected
        can_use, _ = can_user_use_coupon(self.user)
        self.assertFalse(can_use)

        # Admin changes weekly limit to 10 in database
        config = CouponConfiguration.get_config()
        config.weekly_user_limit = 10
        config.save()

        self.assertEqual(CouponConfiguration.get_weekly_limit(), 10)

        # Now user can use up to 10!
        can_use, _ = can_user_use_coupon(self.user)
        self.assertTrue(can_use)

        info = get_user_weekly_coupon_info(self.user)
        self.assertEqual(info["usage_count"], 5)
        self.assertEqual(info["weekly_limit"], 10)
        self.assertEqual(info["remaining"], 5)
        self.assertFalse(info["is_limit_reached"])

    # -------------------------------------------------------------------------
    # TEST 21: Payment completion automatically triggers record_coupon_usage
    # -------------------------------------------------------------------------
    def test_21_payment_save_automatically_records_usage_when_coupon_set(self):
        order = Order.objects.create(
            user=self.user,
            order_number="ORD-AUTO-PAY-1",
            status="confirmed",
            total_amount=Decimal("1600.00"),
            coupon=self.coupon_pct,
            discount_amount=Decimal("400.00"),
            shipping_name="Test Recipient",
            shipping_phone="9876543210",
            shipping_city="Mumbai",
            shipping_pincode="400001",
            shipping_address="123 Test Street, Mumbai",
        )
        self.assertEqual(CouponUsage.objects.filter(order=order).count(), 0)

        payment = Payment.objects.create(
            user=self.user,
            order=order,
            payment_method="card",
            transaction_id="TXN-AUTO-PAY-1",
            amount=Decimal("1600.00"),
            status="completed",
            paid_at=timezone.now(),
        )

        # Verify CouponUsage was created automatically by Payment.save()
        self.assertEqual(CouponUsage.objects.filter(order=order).count(), 1)
        usage = CouponUsage.objects.get(order=order)
        self.assertEqual(usage.discount_amount, Decimal("400.00"))
        self.assertEqual(get_user_weekly_coupon_usage(self.user), 1)
        self.coupon_pct.refresh_from_db()
        self.assertEqual(self.coupon_pct.used_count, 1)

    # -------------------------------------------------------------------------
    # TEST 22: Public coupon list displays active coupons
    # -------------------------------------------------------------------------
    def test_22_public_coupon_list_displays_available_coupons(self):
        response = self.client.get(reverse("coupons:coupon_list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "coupons/public_coupon_list.html")
        self.assertContains(response, "SAVE20")
        self.assertContains(response, "FLAT200")

    # -------------------------------------------------------------------------
    # TEST 23: Checkout page displays available coupons
    # -------------------------------------------------------------------------
    def test_23_checkout_displays_available_coupons(self):
        from apps.products.models import Product, ProductVariant
        from apps.cart.models import Cart, CartItem

        prod = Product.objects.create(name="Test Item", brand="Test Brand", is_active=True)
        var = ProductVariant.objects.create(product=prod, sku="SKU-COUPON-TEST", price=Decimal("1500.00"))
        cart, _ = Cart.objects.get_or_create(user=self.user)
        CartItem.objects.create(cart=cart, product=var, quantity=1)

        self.client.login(username="testuser", password="password123")
        response = self.client.get(reverse("checkout"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("available_coupons", response.context)
        self.assertContains(response, "Available Coupons")
        self.assertContains(response, "SAVE20")
        self.assertContains(response, "FLAT200")
