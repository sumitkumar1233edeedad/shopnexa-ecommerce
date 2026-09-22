import logging
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.db.models import Q
from rest_framework import status
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView 

from apps.chat.models import Conversation, Message
from .serializers import (
    ConversationCreateSerializer,
    ConversationDetailSerializer,
    ConversationListSerializer,
    ConversationStatusUpdateSerializer,
    MessageCreateSerializer,
    MessageSerializer,
)

logger = logging.getLogger(__name__)


# ==============================================================================
# PERMISSION: STAFF OR SUPERUSER RBAC PERMISSION
# ==============================================================================
class IsStaffOrSuperuser(BasePermission):
    """
    Custom permission for Chat Support management:
    - Superuser / Admin -> full unconditional access.
    - Staff user -> Allowed if they have the specific model permission
      (e.g. 'chat.view_conversation', 'chat.add_message', 'chat.change_conversation')
      or if granted custom 'is_prem' / manager rights.
    - Regular customers -> Rejected with HTTP 403 Forbidden.
    """
    message = "Permission denied. You do not have the required chat permission."

    @classmethod
    def check_user(cls, user, required_permission=None):
        """
        Reusable static/class method to check if a user qualifies
        as staff/superuser with the specified permission.
        """
        if not user or not user.is_authenticated:
            return False

        # 1. Superuser / Admin -> full unconditional access
        if user.is_superuser:
            return True

        # 2. Staff user or user flagged with custom 'is_prem'
        if user.is_staff or getattr(user, "is_prem", False):
            # If no granular permission specified, any staff member is permitted
            if not required_permission:
                return True

            # Check Django's built-in RBAC permission system (e.g. user.has_perm("chat.view_conversation"))
            if user.has_perm(required_permission):
                return True

            # If staff has a custom is_prem flag or attribute granted to them
            if getattr(user, "is_prem", False):
                return True

        return False

    def has_permission(self, request, view):
        required_permission = getattr(view, "required_permission", None)
        return self.check_user(request.user, required_permission)


def _can_staff_view_all_chats(user):
    """
    Helper wrapper around IsStaffOrSuperuser for checking 'chat.view_conversation'.
    """
    return IsStaffOrSuperuser.check_user(user, "chat.view_conversation")


def _broadcast_chat_message(conversation_slug, message):
    """
    Broadcasts message to Django Channels WebSocket group in real-time.
    """
    try:
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"chat_{conversation_slug}",
                {
                    "type": "chat_message",
                    "message_id": message.id,
                    "message": message.message,
                    "sender_id": message.sender.id,
                    "sender_name": message.sender.username,
                    "is_staff": message.sender.is_staff,
                    "created_at": message.created_at.strftime("%Y-%m-%d %H:%M"),
                },
            )
    except Exception as e:
        logger.warning("Could not broadcast chat message via channel layer: %s", e)


def _broadcast_status_change(conversation_slug, new_status, status_display):
    """
    Broadcasts status change event to Django Channels WebSocket group.
    """
    try:
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"chat_{conversation_slug}",
                {
                    "type": "status_broadcast",
                    "status": new_status,
                    "status_display": status_display,
                },
            )
    except Exception as e:
        logger.warning("Could not broadcast chat status change: %s", e)


# ==============================================================================
# 1. CONVERSATION LIST & CREATE API VIEW
# ==============================================================================
class ConversationListCreateAPIView(APIView):
    """
    GET  /api/chat/conversations/
        - Customer: lists their own support conversations.
        - Staff with 'chat.view_conversation': lists all conversations (supports ?status=, ?q=).
    POST /api/chat/conversations/
        - Creates a new support ticket / conversation thread.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        # Staff with permission sees all customer conversations
        if IsStaffOrSuperuser.check_user(user, "chat.view_conversation"):
            conversations = (
                Conversation.objects
                .select_related("user")
                .prefetch_related("messages__sender")
                .order_by("-updated_at")
            )

            status_param = request.query_params.get("status", "").strip()
            if status_param and status_param in dict(Conversation.STATUS_CHOICES):
                conversations = conversations.filter(status=status_param)

            query = (request.query_params.get("q") or request.query_params.get("search") or "").strip()
            if query:
                conversations = conversations.filter(
                    Q(user__username__icontains=query)
                    | Q(user__email__icontains=query)
                    | Q(user__first_name__icontains=query)
                    | Q(user__last_name__icontains=query)
                    | Q(slug__icontains=query)
                )
        else:
            # Customer sees only their own conversations
            conversations = (
                Conversation.objects
                .filter(user=user)
                .prefetch_related("messages__sender")
                .order_by("-updated_at")
            )

        serializer = ConversationListSerializer(conversations, many=True, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = ConversationCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        conversation = serializer.save()

        detail_serializer = ConversationDetailSerializer(conversation, context={"request": request})
        return Response(
            {
                "success": True,
                "message": "Support ticket created successfully.",
                "conversation": detail_serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )


# ==============================================================================
# 2. CONVERSATION DETAIL & STATUS UPDATE API VIEW
# ==============================================================================
class ConversationDetailAPIView(APIView):
    """
    GET   /api/chat/conversations/<slug>/
        - Retrieves thread and messages. Automatically marks incoming messages as read.
    PATCH /api/chat/conversations/<slug>/
        - Updates ticket status ('open', 'pending', 'resolved', 'closed').
        - Staff requires 'chat.change_conversation'.
        - Customers can only change their own ticket to 'closed'.
    """
    def get_permissions(self):
        # PATCH requires authentication
        return [IsAuthenticated()]

    def _get_conversation(self, slug, user):
        conversation = (
            Conversation.objects
            .select_related("user")
            .prefetch_related("messages__sender")
            .filter(slug=slug)
            .first()
        )
        if not conversation:
            return None, Response({"error": "Conversation not found."}, status=status.HTTP_404_NOT_FOUND)

        # Access check: owner OR staff with 'chat.view_conversation'
        if not (conversation.user_id == user.id or IsStaffOrSuperuser.check_user(user, "chat.view_conversation")):
            return None, Response(
                {"error": "You do not have permission to view this conversation."},
                status=status.HTTP_403_FORBIDDEN,
            )

        return conversation, None

    def get(self, request, slug):
        conversation, error_response = self._get_conversation(slug, request.user)
        if error_response:
            return error_response

        # Automatically mark incoming messages as read
        with transaction.atomic():
            if request.user.is_staff:
                conversation.messages.exclude(sender__is_staff=True).filter(is_read=False).update(is_read=True)
            else:
                conversation.messages.exclude(sender=request.user).filter(is_read=False).update(is_read=True)

        serializer = ConversationDetailSerializer(conversation, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request, slug):
        conversation, error_response = self._get_conversation(slug, request.user)
        if error_response:
            return error_response

        # Permission check using IsStaffOrSuperuser logic with 'chat.change_conversation'
        is_staff_allowed = IsStaffOrSuperuser.check_user(request.user, "chat.change_conversation")
        is_customer_closing_own = (conversation.user_id == request.user.id and request.data.get("status") == "closed")

        if not (is_staff_allowed or is_customer_closing_own):
            return Response(
                {"error": "Permission denied. You do not have 'chat.change_conversation' permission to change ticket status."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = ConversationStatusUpdateSerializer(conversation, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated_conversation = serializer.save()

        _broadcast_status_change(
            conversation.slug,
            updated_conversation.status,
            updated_conversation.get_status_display(),
        )

        return Response(
            {
                "success": True,
                "message": f"Ticket status changed to {updated_conversation.get_status_display()}.",
                "slug": updated_conversation.slug,
                "status": updated_conversation.status,
                "status_display": updated_conversation.get_status_display(),
            },
            status=status.HTTP_200_OK,
        )


# ==============================================================================
# 3. MESSAGE LIST & CREATE API VIEW
# ==============================================================================
class MessageListCreateAPIView(APIView):
    """
    GET  /api/chat/conversations/<slug>/messages/
        - Retrieves all messages in a conversation.
    POST /api/chat/conversations/<slug>/messages/
        - Sends a new message in the conversation.
        - Staff requires 'chat.add_message' permission.
        - Customers can send messages only to their own conversation.
    """
    def get_permissions(self):
        return [IsAuthenticated()]

    def _get_conversation(self, slug, user):
        conversation = Conversation.objects.select_related("user").filter(slug=slug).first()
        if not conversation:
            return None, Response({"error": "Conversation not found."}, status=status.HTTP_404_NOT_FOUND)

        if not (conversation.user_id == user.id or IsStaffOrSuperuser.check_user(user, "chat.view_conversation")):
            return None, Response(
                {"error": "You do not have permission to access messages in this conversation."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return conversation, None

    def get(self, request, slug):
        conversation, error_response = self._get_conversation(slug, request.user)
        if error_response:
            return error_response

        messages = conversation.messages.select_related("sender").order_by("created_at")
        serializer = MessageSerializer(messages, many=True, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, slug):
        conversation, error_response = self._get_conversation(slug, request.user)
        if error_response:
            return error_response

        # Check permission: Customer can reply to own ticket. Staff requires 'chat.add_message'
        if request.user.is_staff:
            if not IsStaffOrSuperuser.check_user(request.user, "chat.add_message"):
                return Response(
                    {"error": "Permission denied. Staff requires 'chat.add_message' permission to reply."},
                    status=status.HTTP_403_FORBIDDEN,
                )
        else:
            if conversation.user_id != request.user.id:
                return Response(
                    {"error": "You can only send messages in your own support ticket."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        serializer = MessageCreateSerializer(
            data=request.data,
            context={"request": request, "conversation": conversation},
        )
        serializer.is_valid(raise_exception=True)
        message = serializer.save()

        _broadcast_chat_message(conversation.slug, message)

        return Response(
            MessageSerializer(message, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


# ==============================================================================
# 4. MARK MESSAGES READ API VIEW
# ==============================================================================
class ConversationMarkReadAPIView(APIView):
    """
    POST /api/chat/conversations/<slug>/mark-read/
    Explicitly marks all incoming messages in the conversation as read.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, slug):
        conversation = Conversation.objects.filter(slug=slug).first()
        if not conversation:
            return Response({"error": "Conversation not found."}, status=status.HTTP_404_NOT_FOUND)

        if not (conversation.user_id == request.user.id or IsStaffOrSuperuser.check_user(request.user, "chat.view_conversation")):
            return Response({"error": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

        with transaction.atomic():
            if request.user.is_staff:
                updated_count = (
                    conversation.messages
                    .exclude(sender__is_staff=True)
                    .filter(is_read=False)
                    .update(is_read=True)
                )
            else:
                updated_count = (
                    conversation.messages
                    .exclude(sender=request.user)
                    .filter(is_read=False)
                    .update(is_read=True)
                )

        return Response(
            {
                "success": True,
                "message": f"{updated_count} messages marked as read.",
                "unread_count": 0,
            },
            status=status.HTTP_200_OK,
        )


# ==============================================================================
# 5. ADMIN CHAT DASHBOARD STATS API VIEW
# ==============================================================================
class ChatStatsAPIView(APIView):
    """
    GET /api/chat/stats/
    Returns ticket counts grouped by status and total unread count.
    Protected by IsStaffOrSuperuser with 'chat.view_conversation'.
    """
    permission_classes = [IsStaffOrSuperuser]
    required_permission = "chat.view_conversation"

    def get(self, request):
        total_unread = (
            Message.objects
            .filter(is_read=False)
            .exclude(sender__is_staff=True)
            .count()
        )

        data = {
            "all": Conversation.objects.count(),
            "open": Conversation.objects.filter(status="open").count(),
            "pending": Conversation.objects.filter(status="pending").count(),
            "resolved": Conversation.objects.filter(status="resolved").count(),
            "closed": Conversation.objects.filter(status="closed").count(),
            "total_unread": total_unread,
        }
        return Response(data, status=status.HTTP_200_OK)
