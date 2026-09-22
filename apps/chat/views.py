from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q
from apps.admin_pannel.decorators import staff_perm_required
from .models import Conversation, Message
from apps.cart.utils import get_cart_count


@login_required(login_url="login")
def customer_chat(request, conversation_slug=None):
    """
    Customer chat view.
    Loads active conversation by slug, marks staff replies as read, and renders chat interface.
    """
    # 1. Superuser always has access to admin chat system
    if request.user.is_superuser:
        return redirect("admin_chat_list")

    # 2. Staff member WITH Chat permission redirects to admin chat list
    if request.user.is_staff and request.user.has_perm("chat.view_conversation"):
        return redirect("admin_chat_list")

    # 3. Staff member WITHOUT Chat permission & normal customers remain in customer chat
    user_conversations = Conversation.objects.filter(user=request.user).order_by("-updated_at")

    if conversation_slug:
        active_conversation = get_object_or_404(
            Conversation,
            slug=conversation_slug,
            user=request.user
        )
    else:
        # Prefer active (open or pending) conversation
        active_conversation = user_conversations.filter(
            status__in=["open", "pending"]
        ).first()

        # If none open/pending, check for any existing conversation
        if not active_conversation:
            active_conversation = user_conversations.first()

        # If user has no conversations at all, create an initial open conversation
        if not active_conversation:
            active_conversation = Conversation.objects.create(
                user=request.user,
                status="open"
            )

    # Mark incoming replies as read (messages sent by other party)
    active_conversation.messages.exclude(
        sender=request.user
    ).filter(is_read=False).update(is_read=True)

    chat_messages = active_conversation.messages.select_related("sender").order_by("created_at")

    # Annotate unread count for sidebar conversation list
    conversations_with_counts = []
    for conv in user_conversations:
        unread = conv.messages.exclude(sender=request.user).filter(is_read=False).count()
        conversations_with_counts.append({
            "conversation": conv,
            "unread_count": unread,
            "last_message": conv.last_message(),
        })

    cart_count = get_cart_count(request)

    context = {
        "active_conversation": active_conversation,
        "chat_messages": chat_messages,
        "conversations": conversations_with_counts,
        "status_choices": Conversation.STATUS_CHOICES,
        "cart_count": cart_count,
    }
    return render(request, "chat/customer_chat.html", context)


@login_required(login_url="login")
def start_new_conversation(request):
    """
    Creates a new support ticket / conversation for the customer and redirects via slug.
    Superusers and staff with chat permissions are directed to admin chat list.
    """
    if request.user.is_superuser or (request.user.is_staff and request.user.has_perm("chat.view_conversation")):
        return redirect("admin_chat_list")

    if request.method == "POST":
        conv = Conversation.objects.create(
            user=request.user,
            status="open"
        )
        messages.success(request, "New support ticket created.")
        return redirect("chat:customer_chat_detail", conversation_slug=conv.slug)

    return redirect("chat:customer_chat")


# ==============================================================================
# ADMIN CHAT VIEWS (SLUG-BASED)
# ==============================================================================

@staff_perm_required("chat.view_conversation")
def admin_chat_list(request):
    """
    Admin panel list view showing all customer conversations with filters,
    unread badges, and last message previews.
    Requires staff status and 'chat.view_conversation' (or superuser).
    """
    status_filter = request.GET.get("status", "all")
    search_query = request.GET.get("q", "").strip()

    conversations = Conversation.objects.select_related("user").order_by("-updated_at")

    if status_filter != "all" and status_filter in dict(Conversation.STATUS_CHOICES):
        conversations = conversations.filter(status=status_filter)

    if search_query:
        conversations = conversations.filter(
            Q(user__username__icontains=search_query) |
            Q(user__email__icontains=search_query) |
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query)
        )

    # Calculate unread counts and last message per conversation
    conv_list = []
    total_unread = 0
    for conv in conversations:
        unread = conv.messages.filter(is_read=False).exclude(sender__is_staff=True).count()
        total_unread += unread
        conv_list.append({
            "conv": conv,
            "unread_count": unread,
            "last_message": conv.last_message(),
        })

    # Counts by status for tabs
    counts = {
        "all": Conversation.objects.count(),
        "open": Conversation.objects.filter(status="open").count(),
        "pending": Conversation.objects.filter(status="pending").count(),
        "resolved": Conversation.objects.filter(status="resolved").count(),
        "closed": Conversation.objects.filter(status="closed").count(),
        "total_unread": total_unread,
    }

    context = {
        "conversations": conv_list,
        "current_status": status_filter,
        "search_query": search_query,
        "counts": counts,
    }
    return render(request, "adminpanel/admin_chat_list.html", context)


@staff_perm_required("chat.view_conversation")
def admin_chat_room(request, slug):
    """
    Admin real-time chat room for a specific customer conversation identified by slug.
    Requires staff status and 'chat.view_conversation' (or superuser).
    Granular permissions:
    - 'chat.add_message' required to send replies.
    - 'chat.change_conversation' required to update ticket status.
    """
    conversation = get_object_or_404(
        Conversation.objects.select_related("user"),
        slug=slug
    )

    # Mark customer's messages as read
    conversation.messages.exclude(sender__is_staff=True).filter(is_read=False).update(is_read=True)

    chat_messages = conversation.messages.select_related("sender").order_by("created_at")

    # Customer profile info if available
    customer_profile = getattr(conversation.user, "profile", None)

    can_send_message = request.user.is_superuser or request.user.has_perm("chat.add_message")
    can_change_status = request.user.is_superuser or request.user.has_perm("chat.change_conversation")

    context = {
        "conversation": conversation,
        "chat_messages": chat_messages,
        "customer_profile": customer_profile,
        "status_choices": Conversation.STATUS_CHOICES,
        "can_send_message": can_send_message,
        "can_change_status": can_change_status,
    }
    return render(request, "adminpanel/admin_chat_room.html", context)


@staff_perm_required("chat.change_conversation")
def admin_chat_status(request, slug):
    """
    Endpoint for admin to update conversation status via HTTP POST (or AJAX fallback) by slug.
    Requires staff status and 'chat.change_conversation' (or superuser).
    """
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    if request.method == "POST":
        conversation = get_object_or_404(Conversation, slug=slug)
        new_status = request.POST.get("status", "").strip()

        if new_status in dict(Conversation.STATUS_CHOICES):
            conversation.status = new_status
            conversation.save(update_fields=["status", "updated_at"])
            messages.success(request, f"Ticket ({conversation.slug}) status changed to {new_status.capitalize()}.")

        if is_ajax:
            return JsonResponse({"status": "success", "new_status": new_status})

        return redirect("admin_chat_room", slug=conversation.slug)

    return redirect("admin_chat_list")
