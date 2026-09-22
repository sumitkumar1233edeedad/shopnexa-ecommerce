from django.test import TestCase, TransactionTestCase, Client, override_settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse
from channels.testing import WebsocketCommunicator
from ai_store.asgi import application
from apps.chat.models import Conversation, Message

User = get_user_model()


class ChatModelTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            username="testcustomer",
            email="customer@example.com",
            password="testpassword123"
        )
        self.staff = User.objects.create_user(
            username="teststaff",
            email="staff@example.com",
            password="testpassword123",
            is_staff=True
        )

    def test_conversation_creation_and_defaults(self):
        conv = Conversation.objects.create(user=self.customer)
        self.assertEqual(conv.status, "open")
        self.assertEqual(conv.user, self.customer)
        self.assertIn("Conversation", str(conv))

    def test_message_creation_and_unread_counts(self):
        conv = Conversation.objects.create(user=self.customer)

        # Customer sends message
        msg1 = Message.objects.create(
            conversation=conv,
            sender=self.customer,
            message="Hello, I need help with my order."
        )
        # Staff should see 1 unread message
        self.assertEqual(conv.unread_count_for_user(self.staff), 1)
        # Customer should see 0 unread messages (they sent it)
        self.assertEqual(conv.unread_count_for_user(self.customer), 0)

        # Staff replies
        msg2 = Message.objects.create(
            conversation=conv,
            sender=self.staff,
            message="Hi! Sure, what is your order ID?"
        )
        # Customer should now see 1 unread message
        self.assertEqual(conv.unread_count_for_user(self.customer), 1)
        # Staff should see 1 unread message (from customer)
        self.assertEqual(conv.unread_count_for_user(self.staff), 1)

        # Mark customer's message as read
        msg1.is_read = True
        msg1.save()
        self.assertEqual(conv.unread_count_for_user(self.staff), 0)


class ChatPermissionViewTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Permissions
        self.perm_view_conv = Permission.objects.get(
            codename="view_conversation", content_type__app_label="chat"
        )
        self.perm_add_msg = Permission.objects.get(
            codename="add_message", content_type__app_label="chat"
        )
        self.perm_change_conv = Permission.objects.get(
            codename="change_conversation", content_type__app_label="chat"
        )

        # 1. Superuser
        self.superuser = User.objects.create_superuser(
            username="superuser",
            email="super@example.com",
            password="password123"
        )

        # 2. Staff WITH Chat permission (view_conversation)
        self.staff_with_chat_perm = User.objects.create_user(
            username="staff_chat_perm",
            email="staffchat@example.com",
            password="password123",
            is_staff=True
        )
        self.staff_with_chat_perm.user_permissions.add(self.perm_view_conv)

        # 3. Staff WITHOUT Chat permission
        self.staff_no_chat_perm = User.objects.create_user(
            username="staff_no_chat_perm",
            email="staffnochat@example.com",
            password="password123",
            is_staff=True
        )

        # 4. Normal customer
        self.customer = User.objects.create_user(
            username="normal_customer",
            email="customer@example.com",
            password="password123"
        )

        # Another customer
        self.other_customer = User.objects.create_user(
            username="other_customer",
            email="other@example.com",
            password="password123"
        )

        self.conv = Conversation.objects.create(user=self.customer)

    # --------------------------------------------------------------------------
    # 1. Superuser Tests
    # --------------------------------------------------------------------------
    def test_superuser_redirected_from_customer_chat_to_admin_chat_list(self):
        self.client.login(username="superuser", password="password123")
        res = self.client.get(reverse("chat:customer_chat"))
        self.assertRedirects(res, reverse("admin_chat_list"))

    def test_superuser_can_access_admin_chat_list_and_room(self):
        self.client.login(username="superuser", password="password123")
        res_list = self.client.get(reverse("admin_chat_list"))
        self.assertEqual(res_list.status_code, 200)

        res_room = self.client.get(reverse("admin_chat_room", args=[self.conv.slug]))
        self.assertEqual(res_room.status_code, 200)
        self.assertTrue(res_room.context["can_send_message"])
        self.assertTrue(res_room.context["can_change_status"])

    def test_superuser_can_update_status(self):
        self.client.login(username="superuser", password="password123")
        res = self.client.post(
            reverse("admin_chat_status", args=[self.conv.slug]),
            {"status": "resolved"}
        )
        self.assertRedirects(res, reverse("admin_chat_room", args=[self.conv.slug]))
        self.conv.refresh_from_db()
        self.assertEqual(self.conv.status, "resolved")

    # --------------------------------------------------------------------------
    # 2. Staff member WITH Chat permission
    # --------------------------------------------------------------------------
    def test_staff_with_chat_perm_redirected_from_customer_chat_to_admin_chat_list(self):
        self.client.login(username="staff_chat_perm", password="password123")
        res = self.client.get(reverse("chat:customer_chat"))
        self.assertRedirects(res, reverse("admin_chat_list"))

    def test_staff_with_chat_perm_can_access_admin_chat_list_and_room(self):
        self.client.login(username="staff_chat_perm", password="password123")
        res_list = self.client.get(reverse("admin_chat_list"))
        self.assertEqual(res_list.status_code, 200)

        res_room = self.client.get(reverse("admin_chat_room", args=[self.conv.slug]))
        self.assertEqual(res_room.status_code, 200)
        # Without add_message or change_conversation, these flags should be False
        self.assertFalse(res_room.context["can_send_message"])
        self.assertFalse(res_room.context["can_change_status"])

    def test_staff_with_view_perm_denied_status_update_without_change_perm(self):
        self.client.login(username="staff_chat_perm", password="password123")
        res = self.client.post(
            reverse("admin_chat_status", args=[self.conv.slug]),
            {"status": "resolved"}
        )
        # Must deny access and redirect to admin_dashboard
        self.assertRedirects(res, reverse("admin_dashboard"))
        self.conv.refresh_from_db()
        self.assertEqual(self.conv.status, "open")

        # Test AJAX denial
        res_ajax = self.client.post(
            reverse("admin_chat_status", args=[self.conv.slug]),
            {"status": "resolved"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
        self.assertEqual(res_ajax.status_code, 403)

    def test_staff_with_change_conv_perm_can_update_status(self):
        self.staff_with_chat_perm.user_permissions.add(self.perm_change_conv)
        self.staff_with_chat_perm = User.objects.get(id=self.staff_with_chat_perm.id)

        self.client.login(username="staff_chat_perm", password="password123")
        res = self.client.post(
            reverse("admin_chat_status", args=[self.conv.slug]),
            {"status": "pending"}
        )
        self.assertRedirects(res, reverse("admin_chat_room", args=[self.conv.slug]))
        self.conv.refresh_from_db()
        self.assertEqual(self.conv.status, "pending")

    # --------------------------------------------------------------------------
    # 3. Staff member WITHOUT Chat permission
    # --------------------------------------------------------------------------
    def test_staff_without_chat_perm_remains_in_customer_chat(self):
        self.client.login(username="staff_no_chat_perm", password="password123")
        res = self.client.get(reverse("chat:customer_chat"))
        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res, "chat/customer_chat.html")

    def test_staff_without_chat_perm_denied_access_to_admin_chat_list(self):
        self.client.login(username="staff_no_chat_perm", password="password123")
        res = self.client.get(reverse("admin_chat_list"))
        self.assertRedirects(res, reverse("admin_dashboard"))

    def test_staff_without_chat_perm_denied_access_to_admin_chat_room(self):
        self.client.login(username="staff_no_chat_perm", password="password123")
        res = self.client.get(reverse("admin_chat_room", args=[self.conv.slug]))
        self.assertRedirects(res, reverse("admin_dashboard"))

    def test_staff_without_chat_perm_denied_access_to_admin_chat_status(self):
        self.client.login(username="staff_no_chat_perm", password="password123")
        res = self.client.post(
            reverse("admin_chat_status", args=[self.conv.slug]),
            {"status": "closed"}
        )
        self.assertRedirects(res, reverse("admin_dashboard"))

    # --------------------------------------------------------------------------
    # 4. Normal customer Tests
    # --------------------------------------------------------------------------
    def test_normal_customer_remains_in_customer_chat(self):
        self.client.login(username="normal_customer", password="password123")
        res = self.client.get(reverse("chat:customer_chat"))
        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res, "chat/customer_chat.html")

    def test_customer_cannot_access_other_customer_conversation(self):
        conv_other = Conversation.objects.create(user=self.other_customer)
        self.client.login(username="normal_customer", password="password123")
        res = self.client.get(reverse("chat:customer_chat_detail", args=[conv_other.slug]))
        self.assertEqual(res.status_code, 404)

    def test_customer_denied_access_to_admin_chat_list(self):
        self.client.login(username="normal_customer", password="password123")
        res = self.client.get(reverse("admin_chat_list"))
        self.assertRedirects(res, reverse("home"))

    def test_customer_denied_access_to_admin_chat_room(self):
        self.client.login(username="normal_customer", password="password123")
        res = self.client.get(reverse("admin_chat_room", args=[self.conv.slug]))
        self.assertRedirects(res, reverse("home"))

    def test_customer_denied_access_to_admin_chat_status(self):
        self.client.login(username="normal_customer", password="password123")
        res = self.client.post(
            reverse("admin_chat_status", args=[self.conv.slug]),
            {"status": "closed"}
        )
        self.assertRedirects(res, reverse("home"))


@override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class ChatWebSocketTests(TransactionTestCase):
    def setUp(self):
        self.perm_view_conv = Permission.objects.get(
            codename="view_conversation", content_type__app_label="chat"
        )
        self.perm_add_msg = Permission.objects.get(
            codename="add_message", content_type__app_label="chat"
        )
        self.perm_change_conv = Permission.objects.get(
            codename="change_conversation", content_type__app_label="chat"
        )

        self.customer = User.objects.create_user(
            username="ws_customer",
            email="ws@example.com",
            password="password123"
        )
        self.other_customer = User.objects.create_user(
            username="ws_other",
            email="other@example.com",
            password="password123"
        )
        self.staff_no_perm = User.objects.create_user(
            username="ws_staff_no_perm",
            email="staffnoperm@example.com",
            password="password123",
            is_staff=True
        )
        self.staff_with_view = User.objects.create_user(
            username="ws_staff_view",
            email="staffview@example.com",
            password="password123",
            is_staff=True
        )
        self.staff_with_view.user_permissions.add(self.perm_view_conv)

        self.staff_full = User.objects.create_user(
            username="ws_staff_full",
            email="stafffull@example.com",
            password="password123",
            is_staff=True
        )
        self.staff_full.user_permissions.add(
            self.perm_view_conv, self.perm_add_msg, self.perm_change_conv
        )

        self.superuser = User.objects.create_superuser(
            username="ws_superuser",
            email="wssuper@example.com",
            password="password123"
        )

        self.conv = Conversation.objects.create(user=self.customer)

    async def test_unauthenticated_ws_rejected(self):
        communicator = WebsocketCommunicator(
            application,
            f"/ws/chat/{self.conv.slug}/"
        )
        connected, close_code = await communicator.connect(timeout=5)
        self.assertFalse(connected)
        self.assertEqual(close_code, 4001)

    async def test_unauthorized_customer_rejected(self):
        communicator = WebsocketCommunicator(
            application,
            f"/ws/chat/{self.conv.slug}/"
        )
        communicator.scope["user"] = self.other_customer
        connected, close_code = await communicator.connect(timeout=5)
        self.assertFalse(connected)
        self.assertEqual(close_code, 4003)

    async def test_staff_without_chat_perm_cannot_connect_to_other_customer_conversation(self):
        communicator = WebsocketCommunicator(
            application,
            f"/ws/chat/{self.conv.slug}/"
        )
        communicator.scope["user"] = self.staff_no_perm
        connected, close_code = await communicator.connect(timeout=5)
        self.assertFalse(connected)
        self.assertEqual(close_code, 4003)

    async def test_authorized_customer_connect_and_message(self):
        communicator = WebsocketCommunicator(
            application,
            f"/ws/chat/{self.conv.slug}/"
        )
        communicator.scope["user"] = self.customer
        connected, _ = await communicator.connect(timeout=5)
        self.assertTrue(connected)

        # Send a message
        await communicator.send_json_to({
            "action": "message",
            "message": "Hello from customer WebSocket!"
        })

        response = await communicator.receive_json_from()
        self.assertEqual(response["type"], "message")
        self.assertEqual(response["message"], "Hello from customer WebSocket!")
        self.assertEqual(response["sender_id"], self.customer.id)
        self.assertFalse(response["is_staff"])

        await communicator.disconnect()

    async def test_staff_with_view_perm_cannot_send_message_without_add_perm(self):
        communicator = WebsocketCommunicator(
            application,
            f"/ws/chat/{self.conv.slug}/"
        )
        communicator.scope["user"] = self.staff_with_view
        connected, _ = await communicator.connect(timeout=5)
        self.assertTrue(connected)

        # Attempt to send message without chat.add_message
        await communicator.send_json_to({
            "action": "message",
            "message": "Attempted staff reply"
        })

        response = await communicator.receive_json_from()
        self.assertEqual(response["type"], "error")
        self.assertIn("Permission denied", response["message"])

        await communicator.disconnect()

    async def test_staff_with_view_perm_cannot_change_status_without_change_perm(self):
        communicator = WebsocketCommunicator(
            application,
            f"/ws/chat/{self.conv.slug}/"
        )
        communicator.scope["user"] = self.staff_with_view
        connected, _ = await communicator.connect(timeout=5)
        self.assertTrue(connected)

        # Attempt to change status without chat.change_conversation
        await communicator.send_json_to({
            "action": "status_change",
            "status": "resolved"
        })

        response = await communicator.receive_json_from()
        self.assertEqual(response["type"], "error")
        self.assertIn("Permission denied", response["message"])

        await communicator.disconnect()

    async def test_staff_with_full_perms_can_message_and_change_status(self):
        communicator = WebsocketCommunicator(
            application,
            f"/ws/chat/{self.conv.slug}/"
        )
        communicator.scope["user"] = self.staff_full
        connected, _ = await communicator.connect(timeout=5)
        self.assertTrue(connected)

        # 1. Send reply message
        await communicator.send_json_to({
            "action": "message",
            "message": "Authorized staff reply"
        })
        msg_resp = await communicator.receive_json_from()
        self.assertEqual(msg_resp["type"], "message")
        self.assertEqual(msg_resp["message"], "Authorized staff reply")
        self.assertTrue(msg_resp["is_staff"])

        # 2. Change status
        await communicator.send_json_to({
            "action": "status_change",
            "status": "resolved"
        })
        status_resp = await communicator.receive_json_from()
        self.assertEqual(status_resp["type"], "status_change")
        self.assertEqual(status_resp["status"], "resolved")

        await communicator.disconnect()

    async def test_superuser_can_message_and_change_status(self):
        communicator = WebsocketCommunicator(
            application,
            f"/ws/chat/{self.conv.slug}/"
        )
        communicator.scope["user"] = self.superuser
        connected, _ = await communicator.connect(timeout=5)
        self.assertTrue(connected)

        # 1. Send reply
        await communicator.send_json_to({
            "action": "message",
            "message": "Superuser reply"
        })
        msg_resp = await communicator.receive_json_from()
        self.assertEqual(msg_resp["type"], "message")
        self.assertEqual(msg_resp["message"], "Superuser reply")

        # 2. Change status
        await communicator.send_json_to({
            "action": "status_change",
            "status": "closed"
        })
        status_resp = await communicator.receive_json_from()
        self.assertEqual(status_resp["type"], "status_change")
        self.assertEqual(status_resp["status"], "closed")

        await communicator.disconnect()
