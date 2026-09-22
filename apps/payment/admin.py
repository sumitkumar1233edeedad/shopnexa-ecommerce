from django.contrib import admin
from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "user",
        "payment_method",
        "transaction_id",
        "amount",
        "status",
        "paid_at",
        "created_at",
        "slug",
    )
    list_filter = ("payment_method", "status", "created_at")
    search_fields = (
        "order__order_number",
        "order__slug",
        "transaction_id",
        "user__username",
        "user__email",
        "slug",
    )
    readonly_fields = ("transaction_id", "paid_at", "slug", "created_at", "updated_at")
    autocomplete_fields = ("user", "order")
    date_hierarchy = "created_at"
    list_select_related = ("user", "order")
    ordering = ("-created_at",)
