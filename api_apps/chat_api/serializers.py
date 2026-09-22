from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import serializers

from apps.chat.models import Conversation, Message

User = get_user_model()


# ==============================================================================
# 1. USER CHAT SERIALIZER (Compact user representation for chat messages)
# ==============================================================================
class UserChatSerializer(serializers.ModelSerializer):
    """
    Lightweight user representation for embedding inside chat messages
    and conversation participants.
    """
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "is_staff",
        ]
        read_only_fields = fields

    def get_full_name(self, obj):
        name = f"{obj.first_name or ''} {obj.last_name or ''}".strip()
        return name if name else obj.username


# ==============================================================================
# 2. MESSAGE SERIALIZER (Full representation of an individual chat message)
# ==============================================================================
class MessageSerializer(serializers.ModelSerializer):
    """
    Serializer for reading individual chat messages.
    Includes sender details, conversation slug, and an 'is_me' flag indicating
    whether the message was sent by the currently authenticated user.
    """
    sender = UserChatSerializer(read_only=True)
    conversation_slug = serializers.CharField(source="conversation.slug", read_only=True)
    is_me = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            "id",
            "conversation",
            "conversation_slug",
            "sender",
            "message",
            "is_read",
            "created_at",
            "is_me",
        ]
        read_only_fields = [
            "id",
            "conversation",
            "conversation_slug",
            "sender",
            "is_read",
            "created_at",
            "is_me",
        ]

    def get_is_me(self, obj):
        request = self.context.get("request")
        if request and request.user and request.user.is_authenticated:
            return obj.sender_id == request.user.id
        return False


# ==============================================================================
# 3. MESSAGE CREATE SERIALIZER (Input validator for sending a new chat message)
# ==============================================================================
class MessageCreateSerializer(serializers.ModelSerializer):
    """
    Action serializer for sending a message within a conversation.
    Validates content, automatically sets sender from request context,
    and updates conversation status/timestamp.
    """
    message = serializers.CharField(
        required=True,
        allow_blank=False,
        max_length=5000,
        help_text="Message text content."
    )

    class Meta:
        model = Message
        fields = ["message"]

    def validate_message(self, value):
        cleaned = value.strip()
        if not cleaned:
            raise serializers.ValidationError("Message cannot be blank.")
        return cleaned

    def create(self, validated_data):
        request = self.context["request"]
        conversation = self.context["conversation"]
        message_text = validated_data["message"]

        with transaction.atomic():
            message = Message.objects.create(
                conversation=conversation,
                sender=request.user,
                message=message_text,
                is_read=False,
            )

            # If a closed or resolved ticket receives a new customer message, reopen it
            if not request.user.is_staff and conversation.status in ["resolved", "closed"]:
                conversation.status = "open"
                conversation.save(update_fields=["status", "updated_at"])
            else:
                # Update conversation timestamp
                conversation.save(update_fields=["updated_at"])

        return message


# ==============================================================================
# 4. CONVERSATION MINIMAL SERIALIZER (Lightweight ticket preview)
# ==============================================================================
class ConversationMinimalSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for compact conversation references.
    """
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Conversation
        fields = [
            "id",
            "slug",
            "status",
            "status_display",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


# ==============================================================================
# 5. CONVERSATION LIST SERIALIZER (Inbox / Support Ticket Overview)
# ==============================================================================
class ConversationListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing support conversations in customer inboxes
    or the staff admin panel. Annotates unread counts and last message snippet.
    """
    user = UserChatSerializer(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    unread_count = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            "id",
            "slug",
            "user",
            "status",
            "status_display",
            "unread_count",
            "last_message",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_unread_count(self, obj):
        request = self.context.get("request")
        if not request or not request.user or not request.user.is_authenticated:
            return 0
        return obj.unread_count_for_user(request.user)

    def get_last_message(self, obj):
        msg = obj.last_message()
        if not msg:
            return None
        return {
            "id": msg.id,
            "message": msg.message[:120],
            "sender_username": msg.sender.username,
            "sender_is_staff": msg.sender.is_staff,
            "is_read": msg.is_read,
            "created_at": msg.created_at,
        }


# ==============================================================================
# 6. CONVERSATION DETAIL SERIALIZER (Full Thread View with Message History)
# ==============================================================================
class ConversationDetailSerializer(serializers.ModelSerializer):
    """
    Comprehensive serializer for viewing a single conversation thread
    along with its ordered message history.
    """
    user = UserChatSerializer(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    unread_count = serializers.SerializerMethodField()
    messages = MessageSerializer(many=True, read_only=True)

    class Meta:
        model = Conversation
        fields = [
            "id",
            "slug",
            "user",
            "status",
            "status_display",
            "unread_count",
            "messages",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_unread_count(self, obj):
        request = self.context.get("request")
        if not request or not request.user or not request.user.is_authenticated:
            return 0
        return obj.unread_count_for_user(request.user)


# ==============================================================================
# 7. CONVERSATION CREATE SERIALIZER (Start a new support ticket)
# ==============================================================================
class ConversationCreateSerializer(serializers.Serializer):
    """
    Action serializer for initiating a new support ticket.
    Allows passing an optional initial message.
    """
    initial_message = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=5000,
        help_text="Optional starting message for the support ticket."
    )

    def create(self, validated_data):
        request = self.context["request"]
        initial_message = (validated_data.get("initial_message") or "").strip()

        with transaction.atomic():
            conversation = Conversation.objects.create(
                user=request.user,
                status="open"
            )

            if initial_message:
                Message.objects.create(
                    conversation=conversation,
                    sender=request.user,
                    message=initial_message,
                    is_read=False,
                )

        return conversation


# ==============================================================================
# 8. CONVERSATION STATUS UPDATE SERIALIZER (Staff / Admin Action)
# ==============================================================================
class ConversationStatusUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for staff/admin to update conversation status
    ('open', 'pending', 'resolved', 'closed').
    """
    status = serializers.ChoiceField(
        choices=Conversation.STATUS_CHOICES,
        required=True,
        help_text="New ticket status (open, pending, resolved, closed)."
    )

    class Meta:
        model = Conversation
        fields = ["status"]

    def update(self, instance, validated_data):
        instance.status = validated_data["status"]
        instance.save(update_fields=["status", "updated_at"])
        return instance
