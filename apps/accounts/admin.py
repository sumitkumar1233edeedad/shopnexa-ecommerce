from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from .models import CustomUser, Profile, Address, WishList


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "is_staff",
        "is_active",
        "is_email_verified",
        "is_activated",
    )
    list_filter = (
        "is_staff",
        "is_superuser",
        "is_active",
        "is_email_verified",
        "is_activated",
        "groups",
    )
    search_fields = ("username", "email", "first_name", "last_name")
    filter_horizontal = ("groups", "user_permissions")



@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user_display", "phone", "avatar_preview", "slug")
    search_fields = ("name__username", "name__email", "phone", "slug")
    autocomplete_fields = ("name",)
    readonly_fields = ("slug", "avatar_preview")
    list_select_related = ("name",)
    ordering = ("name__username",)

    @admin.display(description="User", ordering="name__username")
    def user_display(self, obj):
        return obj.name.username

    @admin.display(description="Profile Picture")
    def avatar_preview(self, obj):
        if obj.profile_picture:
            return format_html(
                '<img src="{}" style="width:36px; height:36px; object-fit:cover; border-radius:50%;" />',
                obj.profile_picture.url,
            )
        return "-"


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "user",
        "phone",
        "city",
        "state",
        "pincode",
        "address_type",
        "is_default",
        "slug",
    )
    list_filter = ("state", "city", "address_type", "is_default")
    search_fields = ("user__username", "name", "phone", "city", "pincode", "slug")
    autocomplete_fields = ("user",)
    readonly_fields = ("slug",)
    list_select_related = ("user",)
    ordering = ("-is_default", "name")


@admin.register(WishList)
class WishListAdmin(admin.ModelAdmin):
    list_display = ("user", "product", "created_at", "slug")
    list_filter = ("created_at",)
    search_fields = ("user__username", "product__name", "product__slug", "slug")
    autocomplete_fields = ("user", "product")
    readonly_fields = ("slug", "created_at")
    date_hierarchy = "created_at"
    list_select_related = ("user", "product")
    ordering = ("-created_at",)