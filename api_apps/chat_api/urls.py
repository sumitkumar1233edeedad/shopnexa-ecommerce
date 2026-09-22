from django.urls import path
from .views import (
    ConversationListCreateAPIView,
    ConversationDetailAPIView,
    MessageListCreateAPIView,
    ConversationMarkReadAPIView,
    ChatStatsAPIView,
)

urlpatterns = [
    # Support conversation list (GET) and start new ticket (POST)
    path("chat/conversations/", ConversationListCreateAPIView.as_view(), name="api_chat_conversation_list"),

    # Overview ticket stats (open, pending, unread)
    path("chat/stats/", ChatStatsAPIView.as_view(), name="api_chat_stats"),

    # Conversation details (GET) and status change (PATCH)
    path("chat/conversations/<slug:slug>/", ConversationDetailAPIView.as_view(), name="api_chat_conversation_detail"),

    # Message list (GET) and send message (POST)
    path("chat/conversations/<slug:slug>/messages/", MessageListCreateAPIView.as_view(), name="api_chat_messages"),

    # Mark all messages in ticket as read
    path("chat/conversations/<slug:slug>/mark-read/", ConversationMarkReadAPIView.as_view(), name="api_chat_mark_read"),
]
