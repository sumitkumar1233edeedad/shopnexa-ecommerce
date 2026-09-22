from django.contrib import admin
from .models import Conversation, Message


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ("sender", "message", "is_read", "created_at")


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "status", "created_at", "updated_at")
    list_filter = ("status", "created_at")
    search_fields = ("user__username", "user__email")
    inlines = [MessageInline]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("id", "conversation", "sender", "is_read", "created_at")
    list_filter = ("is_read", "created_at")
    search_fields = ("sender__username", "message")
