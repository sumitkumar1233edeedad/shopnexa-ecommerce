from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

from ai.services import run_ai_chat, arun_ai_chat

User = get_user_model()


class AIChatAPITestCase(TestCase):
    """
    Test suite for AI Chat REST API endpoint:
    POST /api/ai/chat/
    Verifies authentication, payload validation, user scoping, and error handling.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="api_user",
            email="api_user@example.com",
            password="Password123!",
            is_email_verified=True,
            is_activated=True,
        )
        self.client = APIClient()

    def test_chat_unauthenticated_rejected(self):
        """Verify unauthenticated requests are rejected with 401."""
        response = self.client.post("/api/ai/chat/", {"message": "Hello"})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_chat_missing_message_rejected(self):
        """Verify missing message field returns 400."""
        self.client.force_authenticate(user=self.user)
        response = self.client.post("/api/ai/chat/", {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    def test_chat_empty_message_rejected(self):
        """Verify whitespace or empty message returns 400."""
        self.client.force_authenticate(user=self.user)
        response = self.client.post("/api/ai/chat/", {"message": "   "})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    def test_chat_invalid_history_format_rejected(self):
        """Verify non-list chat_history returns 400."""
        self.client.force_authenticate(user=self.user)
        response = self.client.post("/api/ai/chat/", {
            "message": "Hello",
            "chat_history": "invalid-string",
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("ai.services.get_shopping_agent")
    def test_chat_success_authenticated(self, mock_get_agent):
        """Verify authenticated request succeeds and returns 200 with AI response."""
        mock_agent = MagicMock()
        mock_agent.invoke.return_value = {
            "final_response": "We have Nike running shoes in stock starting at ₹120.00.",
            "messages": [],
        }
        mock_get_agent.return_value = mock_agent

        self.client.force_authenticate(user=self.user)
        response = self.client.post("/api/ai/chat/", {
            "message": "Show Nike shoes",
            "chat_history": [],
            "user_id": 99999,  # Malicious injection attempt: must be ignored
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("response", response.data)
        self.assertIn("Nike running shoes", response.data["response"])

    @patch("ai.services.get_shopping_agent")
    def test_service_unauthenticated_raises(self, mock_get_agent):
        """Verify run_ai_chat rejects unauthenticated user."""
        with self.assertRaises(PermissionError):
            run_ai_chat(user=None, message="Test")

    @patch("ai.services.get_shopping_agent")
    def test_service_empty_message_raises(self, mock_get_agent):
        """Verify run_ai_chat rejects empty message."""
        with self.assertRaises(ValueError):
            run_ai_chat(user=self.user, message="")

    def test_assistant_web_view_unauthenticated_redirects(self):
        """Verify anonymous user accessing /ai/ is redirected to login."""
        response = self.client.get("/ai/")
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertIn("/login", response.url)

    def test_assistant_web_view_authenticated(self):
        """Verify authenticated user accessing /ai/ gets 200 OK with assistant template."""
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/ai/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTemplateUsed(response, "ai/assistant.html")
        self.assertContains(response, "STORE AI Concierge")

