from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.core import mail
from django.utils import timezone
from django.conf import settings

from apps.accounts.tasks import (
    generate_and_send_otp,
    send_otp_email_task,
    broadcast_coupon_announcement_task,
)
from apps.coupons.models import Coupon
from ai_store.middleware import UserTimezoneMiddleware

User = get_user_model()


class OTPAndCeleryTaskTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username="testcustomer",
            email="customer@example.com",
            password="password123",
            first_name="Test",
            is_active=True,
            is_email_verified=False,
            is_activated=False
        )

    @patch("apps.accounts.tasks.send_otp_email_task.delay")
    def test_generate_and_send_otp_creates_valid_record(self, mock_delay):
        generate_and_send_otp(self.user, purpose="registration")

        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.temp_otp)
        self.assertEqual(len(self.user.temp_otp), 6)
        self.assertTrue(self.user.temp_otp.isdigit())
        self.assertIsNotNone(self.user.otp_created_at)

        # Expiry is within 10 mins
        self.assertGreater(self.user.otp_created_at, timezone.now() - timedelta(minutes=1))
        mock_delay.assert_called_once_with(
            self.user.email,
            self.user.first_name,
            self.user.temp_otp,
            "registration"
        )

    @patch("apps.accounts.tasks.send_otp_email_task.delay")
    def test_generate_and_send_otp_overwrites_previous_otp(self, mock_delay):
        generate_and_send_otp(self.user, purpose="registration")
        self.user.refresh_from_db()
        first_otp = self.user.temp_otp

        # Generate second OTP
        generate_and_send_otp(self.user, purpose="registration")
        self.user.refresh_from_db()
        second_otp = self.user.temp_otp

        self.assertEqual(len(second_otp), 6)
        self.assertEqual(mock_delay.call_count, 2)

    def test_send_otp_email_task_sends_email(self):
        result = send_otp_email_task("customer@example.com", "Test", "123456", "registration")
        self.assertEqual(len(mail.outbox), 1)
        sent_mail = mail.outbox[0]
        self.assertIn("123456", sent_mail.body)
        self.assertIn("10 minutes", sent_mail.body)
        self.assertEqual(sent_mail.to, ["customer@example.com"])


    def test_broadcast_coupon_announcement_task(self):
        # Create second user with no email
        User.objects.create_user(username="noemail", email="", password="password123", is_active=True)
        # Create inactive user
        User.objects.create_user(username="inactive", email="inactive@example.com", password="password123", is_active=False)

        now = timezone.now()
        coupon = Coupon.objects.create(
            code="FESTIVE50",
            discount_type="percentage",
            discount_value=Decimal("50.00"),
            minimum_order_amount=Decimal("500.00"),
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=7),
            is_active=True
        )

        result = broadcast_coupon_announcement_task(coupon.id)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["customer@example.com"])
        self.assertIn("FESTIVE50", mail.outbox[0].body)
        self.assertIn(settings.SITE_URL, mail.outbox[0].body)


class UserTimezoneMiddlewareTests(TestCase):

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username="tzuser",
            email="tz@example.com",
            password="password123"
        )
        self.middleware = UserTimezoneMiddleware(lambda req: req)

    def test_valid_timezone_cookie(self):
        request = self.factory.get("/")
        request.user = self.user
        request.COOKIES["user_timezone"] = "America/New_York"
        self.middleware(request)

    def test_invalid_timezone_cookie_does_not_crash(self):
        request = self.factory.get("/")
        request.user = self.user
        request.COOKIES["user_timezone"] = "Invalid/Nonexistent_Timezone"
        response = self.middleware(request)
        self.assertIsNotNone(response)


class CustomUserModelTests(TestCase):

    def test_custom_user_creation_and_str(self):
        user = User.objects.create_user(
            username="alice",
            email="alice@example.com",
            password="securepassword123"
        )
        self.assertEqual(str(user), "alice")
        self.assertEqual(user.email, "alice@example.com")

    def test_email_uniqueness_enforced(self):
        User.objects.create_user(
            username="user1",
            email="shared@example.com",
            password="password123"
        )
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            User.objects.create_user(
                username="user2",
                email="shared@example.com",
                password="password123"
            )

    def test_email_clean_normalizes_case_and_whitespace(self):
        user = User(
            username="bob",
            email="  BOB@EXAMPLE.COM  "
        )
        user.clean()
        self.assertEqual(user.email, "bob@example.com")

    def test_user_otp_and_verification_fields(self):
        user = User.objects.create_user(
            username="verifytest",
            email="verifytest@example.com",
            password="password123"
        )
        self.assertFalse(user.is_email_verified)
        self.assertFalse(user.is_activated)
        self.assertIsNone(user.temp_otp)
        self.assertIsNone(user.otp_created_at)

        user.temp_otp = "654321"
        user.is_email_verified = True
        user.is_activated = True
        user.save()

        user.refresh_from_db()
        self.assertEqual(user.temp_otp, "654321")
        self.assertTrue(user.is_email_verified)
        self.assertTrue(user.is_activated)


class AuthFlowIntegrationTests(TestCase):

    @patch("apps.accounts.tasks.send_otp_email_task.delay")
    @patch("apps.accounts.tasks.send_registration_email.delay")
    def test_registration_and_otp_verification_flow(self, mock_reg_email, mock_otp_email):
        # 1. Register a new user
        response = self.client.post("/register/", {
            "first_name": "John",
            "last_name": "Doe",
            "email": "johndoe@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn("/verify-otp/", response.url)

        user = User.objects.get(email="johndoe@example.com")
        self.assertFalse(user.is_active)
        self.assertFalse(user.is_email_verified)
        self.assertFalse(user.is_activated)
        self.assertIsNotNone(user.temp_otp)
        self.assertEqual(len(user.temp_otp), 6)

        # 2. Enter invalid OTP
        response = self.client.post("/verify-otp/", {"otp": "000000"})
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertFalse(user.is_active)

        # 3. Enter valid OTP
        valid_otp = user.temp_otp
        response = self.client.post("/verify-otp/", {"otp": valid_otp})
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, "/")

        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertTrue(user.is_email_verified)
        self.assertTrue(user.is_activated)
        self.assertIsNone(user.temp_otp)
        self.assertIsNone(user.otp_created_at)

    @patch("apps.accounts.tasks.send_otp_email_task.delay")
    def test_forgot_and_reset_password_flow(self, mock_otp_email):
        # Create active, verified user
        user = User.objects.create_user(
            username="resetuser",
            email="resetuser@example.com",
            password="OldPassword123!",
            is_active=True,
            is_email_verified=True,
            is_activated=True
        )

        # 1. Request password reset OTP
        response = self.client.post("/forgot-password/", {"email": "resetuser@example.com"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/verify-reset-otp/", response.url)

        user.refresh_from_db()
        self.assertIsNotNone(user.temp_otp)

        # 2. Verify reset OTP
        response = self.client.post("/verify-reset-otp/", {"otp": user.temp_otp})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/reset-password/", response.url)

        user.refresh_from_db()
        self.assertIsNone(user.temp_otp)

        # 3. Set new password
        response = self.client.post("/reset-password/", {
            "new_password": "NewSecretPassword123!",
            "confirm_password": "NewSecretPassword123!"
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

        user.refresh_from_db()
        self.assertTrue(user.check_password("NewSecretPassword123!"))



