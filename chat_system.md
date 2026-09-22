# 💬 STORE AI — Real-Time Chat Support System Documentation (Slug-Based)

This document explains the complete architecture, setup, code structure, message flow, testing procedures, and troubleshooting for the **Customer-to-Admin Real-Time Chat Support** feature in **STORE AI** using clean, SEO-friendly **slug-based URLs**.

---

## 📌 1. Technology Overview

* **Backend Framework**: Django 6.1+
* **Asynchronous Server Interface (ASGI)**: Django Channels 4.3+ & Daphne 4.2+
* **Real-time Protocol**: WebSockets (`ws://` / `wss://`)
* **In-Memory Channel Layer**: Redis (`channels_redis`)
* **Background Tasks**: Celery (Runs independently on Redis DB 0 without conflict)
* **URL Structure**: Clean, readable **slug-based routing** (e.g. `/chat/ticket-john-a83d7f9b/`, `/ws/chat/ticket-john-a83d7f9b/`)
* **Frontend**: Pure Vanilla HTML5, CSS3, and JavaScript (No external JS frameworks needed)

---

## 🏗️ 2. Architectural Diagram

```text
 ┌─────────────────────────────────────────────────────────────┐
 │               Browser Client (Customer / Admin)              │
 └────────────────────────────┬────────────────────────────────┘
                              │
                              │ WebSocket (ws://127.0.0.1:8000/ws/chat/<slug>/)
                              ▼
 ┌─────────────────────────────────────────────────────────────┐
 │                    Daphne ASGI Server                       │
 │                     (ai_store/asgi.py)                      │
 └────────────────────────────┬────────────────────────────────┘
                              │
              ProtocolTypeRouter + AuthMiddlewareStack
                              │
                              ▼
 ┌─────────────────────────────────────────────────────────────┐
 │               ChatConsumer (consumers.py)                   │
 │  • Authenticates user from Django session                   │
 │  • Verifies permission (Owner customer OR Admin/Staff)      │
 │  • Room group: chat_<conversation_slug>                     │
 └─────────────┬─────────────────────────────────┬─────────────┘
               │                                 │
    1. Save to Database                2. In-Memory Pub/Sub Broadcast
               │                                 │
               ▼                                 ▼
 ┌──────────────────────────┐      ┌──────────────────────────┐
 │    SQLite Database       │      │   Redis Channel Layer    │
 │  - Conversation (slug)   │      │   (127.0.0.1:6379)       │
 │  - Message               │      │   Distributes to room    │
 └──────────────────────────┘      └──────────────────────────┘
```

### Celery vs. Django Channels Separation

| Service | Protocol | Redis Usage | Responsibility |
|---|---|---|---|
| **Django Channels** | WebSockets (`ws://`) | Channel Layer Pub/Sub | Instant, real-time bidirectional messaging between customer and admin |
| **Celery** | HTTP / AMQP Tasks | Redis DB 0 (`redis://127.0.0.1:6379/0`) | Async background workers: OTP sending, email delivery, coupon broadcasting |

---

## 🗄️ 3. Slug-Based Database Models (`apps/chat/models.py`)

Every support ticket automatically generates a unique slug upon creation in the format:
`ticket-<username>-<uuid_hex_8>` (e.g. `ticket-sumitkumar-9fc9383f`).

```python
import uuid
from django.db import models
from django.contrib.auth import get_user_model
from django.utils.text import slugify

User = get_user_model()


class Conversation(models.Model):
    STATUS_CHOICES = [
        ("open", "Open"),
        ("pending", "Pending"),
        ("resolved", "Resolved"),
        ("closed", "Closed"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="conversations"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="open"
    )
    slug = models.SlugField(
        max_length=100,
        unique=True,
        blank=True,
        null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"Conversation #{self.id} ({self.slug}) - {self.user.username} ({self.status})"

    def save(self, *args, **kwargs):
        if not self.slug:
            username_part = slugify(self.user.username) if self.user else "support"
            self.slug = f"ticket-{username_part}-{uuid.uuid4().hex[:8]}"
        super().save(*args, **kwargs)

    def unread_count_for_user(self, user):
        """
        Calculates unread messages:
        - If user is Staff: counts unread customer messages.
        - If user is Customer: counts unread staff messages.
        """
        if user.is_staff:
            return self.messages.filter(is_read=False).exclude(sender__is_staff=True).count()
        return self.messages.filter(is_read=False, sender__is_staff=True).count()

    def last_message(self):
        return self.messages.order_by("-created_at").first()


class Message(models.Model):
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages"
    )
    sender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="chat_messages"
    )
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Message #{self.id} by {self.sender.username} in Conv #{self.conversation_id}"
```

---

## 🔌 4. Slug-Based WebSocket Consumer & Routing

### `apps/chat/routing.py`
```python
from django.urls import path
from . import consumers

websocket_urlpatterns = [
    path("ws/chat/<slug:conversation_slug>/", consumers.ChatConsumer.as_asgi()),
]
```

### `apps/chat/consumers.py`
```python
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from .models import Conversation, Message


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope.get("user")
        self.conversation_slug = self.scope["url_route"]["kwargs"].get("conversation_slug")
        self.room_group_name = f"chat_{self.conversation_slug}"

        # 1. Reject unauthenticated users
        if not self.user or not self.user.is_authenticated:
            await self.close(code=4001)
            return

        # 2. Reject unauthorized users (customer must own ticket or be staff)
        is_authorized = await self.check_user_permission(self.conversation_slug, self.user)
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

        # Chat message sent
        if action == "message":
            raw_text = data.get("message", "").strip()
            if not raw_text:
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

        # Admin updating status live
        elif action == "status_change" and self.user.is_staff:
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

        # Mark messages read
        elif action == "mark_read":
            await self.mark_messages_read(self.conversation_slug, self.user)

    async def chat_message(self, event):
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
        await self.send(text_data=json.dumps({
            "type": "status_change",
            "status": event["status"],
            "status_display": event["status_display"],
        }))

    @database_sync_to_async
    def check_user_permission(self, conversation_slug, user):
        try:
            conv = Conversation.objects.get(slug=conversation_slug)
            return bool(user.is_staff or conv.user_id == user.id)
        except Conversation.DoesNotExist:
            return False

    @database_sync_to_async
    def save_message(self, conversation_slug, user, raw_text):
        try:
            conv = Conversation.objects.get(slug=conversation_slug)
            if conv.status == "closed" and not user.is_staff:
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
            local_time = timezone.localtime(msg.created_at)

            return {
                "id": msg.id,
                "message": msg.message,
                "sender_id": user.id,
                "sender_name": display_name,
                "is_staff": user.is_staff,
                "created_at": local_time.strftime("%I:%M %p"),
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
            if user.is_staff:
                conv.messages.exclude(sender__is_staff=True).filter(is_read=False).update(is_read=True)
            else:
                conv.messages.filter(sender__is_staff=True, is_read=False).update(is_read=True)
        except Exception:
            pass
```

---

## 🌐 5. Slug-Based Views & URLs

### `apps/chat/urls.py`
```python
from django.urls import path
from . import views

app_name = "chat"

urlpatterns = [
    path("", views.customer_chat, name="customer_chat"),
    path("new/", views.start_new_conversation, name="start_new_conversation"),
    path("<slug:conversation_slug>/", views.customer_chat, name="customer_chat_detail"),
]
```

### `apps/admin_pannel/urls.py` (Slug Routes)
```python
from apps.chat import views as chat_views

urlpatterns = [
    # ...
    path("chat/", chat_views.admin_chat_list, name="admin_chat_list"),
    path("chat/<slug:slug>/", chat_views.admin_chat_room, name="admin_chat_room"),
    path("chat/<slug:slug>/status/", chat_views.admin_chat_status, name="admin_chat_status"),
]
```

---

## 💻 6. Client JavaScript (Connecting via Slug)

```javascript
const conversationSlug = "{{ active_conversation.slug }}";
const currentUserId = {{ request.user.id }};
const wsProtocol = window.location.protocol === "https:" ? "wss://" : "ws://";

// Connect to slug-based endpoint
const socket = new WebSocket(wsProtocol + window.location.host + "/ws/chat/" + conversationSlug + "/");

socket.onopen = function(e) {
    document.getElementById("connection-status").textContent = "Connected";
    socket.send(JSON.stringify({ action: "mark_read" }));
};

socket.onmessage = function(e) {
    const data = JSON.parse(e.data);
    if (data.type === "message") {
        appendMessage(data);
        scrollToBottom();
    } else if (data.type === "status_change") {
        updateStatusBadge(data.status, data.status_display);
    }
};

function sendMessage(text) {
    if (socket.readyState === WebSocket.OPEN && text.trim()) {
        socket.send(JSON.stringify({
            action: "message",
            message: text.trim()
        }));
    }
}
```

---

## 🚀 7. Operational Commands

### 1. Start Redis in Docker
```bash
docker run -d --name redis-server -p 6379:6379 redis:latest
```

### 2. Run Django ASGI Server
```bash
python manage.py runserver 127.0.0.1:8000
```

### 3. Run Celery Worker (In a separate terminal)
```powershell
celery -A ai_store worker --pool=solo -l info
```

### 4. Run Automated Test Suite
```powershell
python manage.py test apps.chat
```

---

## 🧪 8. Testing Customer ↔ Admin Messaging (Slug-Based)

1. Start server: `python manage.py runserver 127.0.0.1:8000`.
2. **Customer Window**:
   * Visit `http://127.0.0.1:8000/chat/`.
   * The URL will automatically resolve to your active ticket (e.g. `/chat/ticket-sumitkumar-9fc9383f/`).
   * The status shows **"Connected to Live Support"** (green dot).
3. **Admin Window (Incognito)**:
   * Log in to `http://127.0.0.1:8000/adminpanel/login/`.
   * Navigate to `http://127.0.0.1:8000/adminpanel/chat/`.
   * Click **Open Chat →** on the ticket (`ticket-sumitkumar-9fc9383f`).
4. **Send Customer Message**:
   * Type `"Where is my shipment?"` and send.
   * Result: Instant live appearance in the Admin window with zero page reload.
5. **Send Admin Reply**:
   * Reply `"Out for delivery today!"` and send.
   * Result: Instant live appearance on the customer's screen under "Support Agent".
6. **Change Status**:
   * Change status to `Resolved` in admin.
   * Result: Status badge changes to `RESOLVED` live on both screens.



#### 

|  # | API                                          |   Method  | Token    | JSON Body                                                                    | Purpose                             |
| -: | -------------------------------------------- | :-------: | -------- | ---------------------------------------------------------------------------- | ----------------------------------- |
|  1 | `/api/chat/conversations/`                   |  **POST** | Customer | `{"initial_message":"Hello support, I need help with my order."}`            | Create conversation                 |
|  2 | `/api/chat/conversations/`                   |  **GET**  | Customer | —                                                                            | Get customer's conversations        |
|  3 | `/api/chat/conversations/<slug>/`            |  **GET**  | Customer | —                                                                            | Get conversation detail             |
|  4 | `/api/chat/conversations/<slug>/messages/`   |  **GET**  | Customer | —                                                                            | Get messages                        |
|  5 | `/api/chat/conversations/<slug>/messages/`   |  **POST** | Customer | `{"message":"Can you please check my order status?"}`                        | Customer sends message              |
|  6 | `/api/chat/conversations/`                   |  **GET**  | Staff    | —                                                                            | Staff gets all conversations        |
|  7 | `/api/chat/conversations/<slug>/`            |  **GET**  | Staff    | —                                                                            | Staff gets conversation detail      |
|  8 | `/api/chat/conversations/<slug>/messages/`   |  **POST** | Staff    | `{"message":"I am checking your order status. We will update you shortly."}` | Staff replies                       |
|  9 | `/api/chat/conversations/<slug>/mark-read/`  |  **POST** | Customer | —                                                                            | Mark incoming messages read         |
| 10 | `/api/chat/conversations/<slug>/`            | **PATCH** | Staff    | `{"status":"pending"}`                                                       | Change to pending                   |
| 11 | `/api/chat/conversations/<slug>/`            | **PATCH** | Staff    | `{"status":"resolved"}`                                                      | Change to resolved                  |
| 12 | `/api/chat/conversations/<slug>/`            | **PATCH** | Customer | `{"status":"closed"}`                                                        | Customer closes conversation        |
| 13 | `/api/chat/conversations/?status=open`       |  **GET**  | Staff    | —                                                                            | Filter open                         |
| 14 | `/api/chat/conversations/?status=pending`    |  **GET**  | Staff    | —                                                                            | Filter pending                      |
| 15 | `/api/chat/conversations/?status=resolved`   |  **GET**  | Staff    | —                                                                            | Filter resolved                     |
| 16 | `/api/chat/conversations/?status=closed`     |  **GET**  | Staff    | —                                                                            | Filter closed                       |
| 17 | `/api/chat/conversations/?search=sumit`      |  **GET**  | Staff    | —                                                                            | Search conversations                |
| 18 | `/api/chat/stats/`                           |  **GET**  | Staff    | —                                                                            | Chat statistics                     |
| 19 | `/api/chat/stats/`                           |  **GET**  | Customer | —                                                                            | Permission test → should reject     |
| 20 | `/api/chat/conversations/`                   |  **GET**  | None     | —                                                                            | Authentication test → should reject |
| 21 | `/api/chat/conversations/<other-user-slug>/` |  **GET**  | Customer | —                                                                            | Ownership/security test             |
