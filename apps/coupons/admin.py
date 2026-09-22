from django.contrib import admin
from django.utils import timezone
from .models import Coupon, CouponConfiguration, CouponUsage


class CouponValidityListFilter(admin.SimpleListFilter):
    title = "Validity"
    parameter_name = "validity"

    def lookups(self, request, model_admin):
        return (
            ("valid_now", "Currently Valid"),
            ("expired", "Expired"),
            ("upcoming", "Upcoming / Future"),
        )

    def queryset(self, request, queryset):
        now = timezone.now()
        if self.value() == "valid_now":
            return queryset.filter(valid_from__lte=now, valid_until__gte=now, is_active=True)
        if self.value() == "expired":
            return queryset.filter(valid_until__lt=now)
        if self.value() == "upcoming":
            return queryset.filter(valid_from__gt=now)
        return queryset


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "discount_type",
        "discount_value_display",
        "is_active",
        "valid_from",
        "valid_until",
        "usage_limit_display",
        "used_count",
        "per_user_limit_display",
        "weekly_user_limit_display",
        "created_at",
    )
    list_filter = (
        "is_active",
        "discount_type",
        CouponValidityListFilter,
        "created_at",
    )
    search_fields = (
        "code",
        "description",
    )
    readonly_fields = (
        "used_count",
        "created_at",
        "updated_at",
        "weekly_user_limit_display",
    )
    fieldsets = (
        ("Coupon Information", {
            "fields": ("code", "description", "is_active")
        }),
        ("Discount Configuration", {
            "fields": (
                "discount_type",
                "discount_value",
                "minimum_order_amount",
                "maximum_discount_amount",
            )
        }),
        ("Validity Period", {
            "fields": ("valid_from", "valid_until")
        }),
        ("Usage Limits", {
            "fields": (
                "usage_limit",
                "used_count",
                "per_user_limit",
                "weekly_user_limit_display",
            )
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    @admin.display(description="Discount")
    def discount_value_display(self, obj):
        if obj.discount_type == "percentage":
            return f"{obj.discount_value}%"
        return f"₹{obj.discount_value}"

    @admin.display(description="Global Limit")
    def usage_limit_display(self, obj):
        return obj.usage_limit if obj.usage_limit is not None else "Unlimited"

    @admin.display(description="Per-User Limit")
    def per_user_limit_display(self, obj):
        return obj.per_user_limit if obj.per_user_limit is not None else "Unlimited"

    @admin.display(description="Weekly User Limit")
    def weekly_user_limit_display(self, obj):
        limit = CouponConfiguration.get_weekly_limit()
        return f"{limit} / week (Global)"


@admin.register(CouponConfiguration)
class CouponConfigurationAdmin(admin.ModelAdmin):
    list_display = ("__str__", "weekly_user_limit", "updated_at")
    fields = ("weekly_user_limit",)

    def has_add_permission(self, request):
        # Singleton: allow add only if no configuration instance exists yet
        if CouponConfiguration.objects.exists():
            return False
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        # Disallow deleting the global configuration
        return False


@admin.register(CouponUsage)
class CouponUsageAdmin(admin.ModelAdmin):
    list_display = (
        "coupon",
        "user",
        "order_number_display",
        "discount_amount_display",
        "used_at",
    )
    list_filter = (
        "coupon",
        "used_at",
    )
    search_fields = (
        "coupon__code",
        "user__username",
        "user__email",
        "order__order_number",
    )
    readonly_fields = (
        "coupon",
        "user",
        "order",
        "discount_amount",
        "used_at",
    )
    date_hierarchy = "used_at"

    @admin.display(description="Order Number")
    def order_number_display(self, obj):
        return obj.order.order_number if obj.order else "-"

    @admin.display(description="Discount Given")
    def discount_amount_display(self, obj):
        return f"₹{obj.discount_amount}"

    def has_add_permission(self, request):
        # CouponUsage should only be generated automatically by the order/payment system
        return False
