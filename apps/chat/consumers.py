import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from .models import Conversation, Message


class ChatConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for handling real-time customer-to-admin chat conversations
    using slug-based rooms. Enforces granular authentication and permission-based security:
    - Superusers: Full access to join, view, reply, and change status.
    - Staff WITH 'chat.view_conversation': Can join any room and view messages.
      - Requires 'chat.add_message' to send replies.
      - Requires 'chat.change_conversation' to update status.
    - Staff WITHOUT 'chat.view_conversation': Restricted to their own conversation (acts as customer).
    - Normal customers: Restricted to their own conversation (acts as customer).
    """

    async def connect(self):
        self.user = self.scope.get("user")
        self.conversation_slug = self.scope["url_route"]["kwargs"].get("conversation_slug")
        self.room_group_name = f"chat_{self.conversation_slug}"

        # 1. Reject unauthenticated users
        if not self.user or not self.user.is_authenticated:
            await self.close(code=4001)
            return

        # 2. Enforce authorization based on Django permissions
        is_authorized = await self.check_user_access(self.conversation_slug, self.user)
        if not is_authorized:
            await self.close(code=4003)
            return

        # 3. Join conversation room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        # Leave room group
        if hasattr(self, "room_group_name"):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return

        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return

        action = data.get("action", "message")

        # Customer or Admin sending a chat message
        if action == "message":
            raw_text = data.get("message", "").strip()
            if not raw_text:
                return

            # Verify sending permission
            can_send = await self.check_can_send_message(self.conversation_slug, self.user)
            if not can_send:
                await self.send(text_data=json.dumps({
                    "type": "error",
                    "message": "Permission denied: 'chat.add_message' required to send replies."
                }))
                return

            saved_msg = await self.save_message(self.conversation_slug, self.user, raw_text)
            if saved_msg:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        "type": "chat_message",
                        "message_id": saved_msg["id"],
                        "message": saved_msg["message"],
                        "sender_id": saved_msg["sender_id"],
                        "sender_name": saved_msg["sender_name"],
                        "is_staff": saved_msg["is_staff"],
                        "created_at": saved_msg["created_at"],
                    }
                )

        # Admin updating conversation status in real-time
        elif action == "status_change":
            # Verify status change permission ('chat.change_conversation' or superuser)
            can_change = await self.check_can_change_status(self.conversation_slug, self.user)
            if not can_change:
                await self.send(text_data=json.dumps({
                    "type": "error",
                    "message": "Permission denied: 'chat.change_conversation' required to update status."
                }))
                return

            new_status = data.get("status", "").strip()
            valid_statuses = dict(Conversation.STATUS_CHOICES)
            if new_status in valid_statuses:
                updated = await self.update_status(self.conversation_slug, new_status)
                if updated:
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            "type": "status_broadcast",
                            "status": new_status,
                            "status_display": valid_statuses[new_status],
                        }
                    )

        # Mark messages read when viewing
        elif action == "mark_read":
            await self.mark_messages_read(self.conversation_slug, self.user)
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "read_broadcast",
                    "user_id": self.user.id,
                }
            )

    # Handlers for events sent to the room group
    async def chat_message(self, event):
        """Send message payload to WebSocket."""
        await self.send(text_data=json.dumps({
            "type": "message",
            "message_id": event["message_id"],
            "message": event["message"],
            "sender_id": event["sender_id"],
            "sender_name": event["sender_name"],
            "is_staff": event["is_staff"],
            "created_at": event["created_at"],
        }))

    async def status_broadcast(self, event):
        """Send status update payload to WebSocket."""
        await self.send(text_data=json.dumps({
            "type": "status_change",
            "status": event["status"],
            "status_display": event["status_display"],
        }))

    async def read_broadcast(self, event):
        """Send read receipt notification to WebSocket."""
        await self.send(text_data=json.dumps({
            "type": "read_receipt",
            "user_id": event["user_id"],
        }))

    # Database Helpers
    @database_sync_to_async
    def check_user_access(self, conversation_slug, user):
        """
        Check if user is authorized to join the conversation room:
        - Superuser: Allowed for all rooms.
        - Staff WITH 'chat.view_conversation': Allowed for all rooms.
        - Staff WITHOUT 'chat.view_conversation': Allowed ONLY for their own conversation.
        - Normal customer: Allowed ONLY for their own conversation.
        """
        try:
            conv = Conversation.objects.get(slug=conversation_slug)
        except Conversation.DoesNotExist:
            return False

        if user.is_superuser:
            return True

        if user.is_staff and user.has_perm("chat.view_conversation"):
            return True

        return bool(conv.user_id == user.id)

    @database_sync_to_async
    def check_can_send_message(self, conversation_slug, user):
        """
        Check if user is permitted to send a message:
        - Conversation owner: Allowed (customer sending in own ticket).
        - Staff / Admin replying: Requires superuser or 'chat.add_message' permission.
        """
        try:
            conv = Conversation.objects.get(slug=conversation_slug)
        except Conversation.DoesNotExist:
            return False

        # Conversation owner can always send in their own ticket
        if conv.user_id == user.id:
            return True

        # Staff replying to another user's conversation requires permission
        if user.is_superuser:
            return True

        if user.is_staff and user.has_perm("chat.add_message"):
            return True

        return False

    @database_sync_to_async
    def check_can_change_status(self, conversation_slug, user):
        """
        Check if user is permitted to change conversation status:
        - Requires superuser or staff WITH 'chat.change_conversation' permission.
        """
        try:
            conv = Conversation.objects.get(slug=conversation_slug)
        except Conversation.DoesNotExist:
            return False

        if user.is_superuser:
            return True

        if user.is_staff and user.has_perm("chat.change_conversation"):
            return True

        return False

    @database_sync_to_async
    def save_message(self, conversation_slug, user, raw_text):
        try:
            conv = Conversation.objects.get(slug=conversation_slug)
            is_customer = (conv.user_id == user.id)

            # Reopen closed conversation if customer sends a new message
            if conv.status == "closed" and is_customer:
                conv.status = "open"

            msg = Message.objects.create(
                conversation=conv,
                sender=user,
                message=raw_text,
                is_read=False,
            )
            conv.updated_at = timezone.now()
            conv.save(update_fields=["status", "updated_at"])

            display_name = user.get_full_name() or user.username
            is_staff_reply = bool(user.is_staff and not is_customer)

            return {
                "id": msg.id,
                "message": msg.message,
                "sender_id": user.id,
                "sender_name": display_name,
                "is_staff": is_staff_reply,
                "created_at": msg.created_at.isoformat(),
            }
        except Exception:
            return None

    @database_sync_to_async
    def update_status(self, conversation_slug, new_status):
        try:
            conv = Conversation.objects.get(slug=conversation_slug)
            conv.status = new_status
            conv.updated_at = timezone.now()
            conv.save(update_fields=["status", "updated_at"])
            return True
        except Exception:
            return False

    @database_sync_to_async
    def mark_messages_read(self, conversation_slug, user):
        try:
            conv = Conversation.objects.get(slug=conversation_slug)
            if conv.user_id == user.id:
                # Customer viewing own ticket: mark staff replies as read
                conv.messages.exclude(sender_id=user.id).filter(is_read=False).update(is_read=True)
            elif user.is_superuser or (user.is_staff and user.has_perm("chat.view_conversation")):
                # Staff viewing customer ticket: mark customer messages as read
                conv.messages.filter(sender_id=conv.user_id, is_read=False).update(is_read=True)
            return True
        except Exception:
            return False
