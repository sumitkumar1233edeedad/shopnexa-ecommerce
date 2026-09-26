from unittest.mock import MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from ai.context import set_current_user, get_current_user, reset_current_user

User = get_user_model()


class ContextVarSecurityTestCase(TestCase):
    """
    Tests for ContextVar authenticated user injection, retrieval, and cleanup.
    Guarantees that user context is never leaked across requests or threads.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="test_ctx_user",
            email="test_ctx@example.com",
            password="Password123!",
            is_email_verified=True,
            is_activated=True,
        )

    def test_context_set_get_and_reset(self):
        """Verify setting, retrieving, and resetting authenticated user in context."""
        token = set_current_user(self.user)
        try:
            current = get_current_user()
            self.assertEqual(current, self.user)
            self.assertEqual(current.username, "test_ctx_user")
        finally:
            reset_current_user(token)

        # After reset, accessing context must raise PermissionError
        with self.assertRaises(PermissionError):
            get_current_user()

    def test_context_rejects_none_user(self):
        """Verify set_current_user rejects None."""
        with self.assertRaises(PermissionError):
            set_current_user(None)

    def test_context_rejects_unauthenticated_user(self):
        """Verify set_current_user rejects anonymous or unauthenticated user objects."""
        anon = MagicMock()
        anon.is_authenticated = False
        with self.assertRaises(PermissionError):
            set_current_user(anon)
