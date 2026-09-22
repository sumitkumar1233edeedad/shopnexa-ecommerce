from django.db import models
from django.conf import settings


class Conversation(models.Model):
    """
    Represents a customer support conversation thread between a customer and admin/staff.
    """
    STATUS_CHOICES = [
        ("open", "Open"),
        ("pending", "Pending"),
        ("resolved", "Resolved"),
        ("closed", "Closed"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
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
            import uuid
            from django.utils.text import slugify
            username_part = slugify(self.user.username) if self.user else "support"
            self.slug = f"ticket-{username_part}-{uuid.uuid4().hex[:8]}"
        super().save(*args, **kwargs)

    def unread_count_for_user(self, user):
        """
        Returns number of unread messages for the given user.
        Staff sees unread customer messages; customer sees unread staff replies.
        """
        if user.is_staff:
            return self.messages.filter(is_read=False).exclude(sender__is_staff=True).count()
        return self.messages.filter(is_read=False, sender__is_staff=True).count()

    def last_message(self):
        """
        Returns the most recent message in the conversation.
        """
        return self.messages.order_by("-created_at").first()


class Message(models.Model):
    """
    Represents an individual chat message within a Conversation.
    """
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages"
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
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
