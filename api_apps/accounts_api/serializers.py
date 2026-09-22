from rest_framework import serializers

from apps.accounts.models import (
    CustomUser,
    Profile,
    Address,
    WishList,
)


# =========================================================
# CUSTOM USER SERIALIZER
# =========================================================

class CustomUserSerializer(serializers.ModelSerializer):

    class Meta:
        model = CustomUser

        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "is_email_verified",
            "is_activated",
        ]

        read_only_fields = [
            "id",
            "is_email_verified",
            "is_activated",
        ]


# =========================================================
# PROFILE SERIALIZER
# =========================================================

class ProfileSerializer(serializers.ModelSerializer):

    username = serializers.CharField(
        source="name.username",
        read_only=True
    )

    email = serializers.EmailField(
        source="name.email",
        read_only=True
    )

    first_name = serializers.CharField(
        source="name.first_name",
        required=False
    )

    last_name = serializers.CharField(
        source="name.last_name",
        required=False
    )

    class Meta:
        model = Profile

        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "phone",
            "profile_picture",
            "slug",
        ]

        read_only_fields = [
            "id",
            "username",
            "email",
            "slug",
        ]

    def update(self, instance, validated_data):
        user_data = validated_data.pop("name", {})
        user = instance.name
        user_updated = False
        if "first_name" in user_data:
            user.first_name = user_data["first_name"]
            user_updated = True
        if "last_name" in user_data:
            user.last_name = user_data["last_name"]
            user_updated = True
        if user_updated:
            user.save()

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


# =========================================================
# ADDRESS SERIALIZER
# =========================================================

class AddressSerializer(serializers.ModelSerializer):

    state_display = serializers.CharField(
        source="get_state_display",
        read_only=True
    )

    address_type_display = serializers.CharField(
        source="get_address_type_display",
        read_only=True
    )

    class Meta:
        model = Address

        fields = [
            "id",
            "name",
            "phone",
            "pincode",
            "locality",
            "address_line",
            "city",
            "state",
            "state_display",
            "landmark",
            "address_type",
            "address_type_display",
            "is_default",

            # GPS
            "latitude",
            "longitude",
            "area",
            "formatted_address",

            # slug
            "slug",
        ]

        read_only_fields = [
            "id",
            "state_display",
            "address_type_display",
            "slug",
        ]

    def to_internal_value(self, data):
        data = data.copy() if hasattr(data, "copy") else dict(data)

        # Support 'full_name' alias from forms/clients
        if "full_name" in data and "name" not in data:
            data["name"] = data["full_name"]

        # Clean empty coordinates
        if data.get("latitude") == "":
            data["latitude"] = None
        if data.get("longitude") == "":
            data["longitude"] = None

        # Flexible state matching (accepts either state code or state name)
        state_val = data.get("state")
        if state_val:
            state_val_clean = str(state_val).strip()
            valid_keys = dict(Address.STATE_CHOICES)
            if state_val_clean.upper() in valid_keys:
                data["state"] = state_val_clean.upper()
            else:
                name_to_code = {name.lower(): code for code, name in Address.STATE_CHOICES}
                if state_val_clean.lower() in name_to_code:
                    data["state"] = name_to_code[state_val_clean.lower()]

        return super().to_internal_value(data)



# =========================================================
# WISHLIST SERIALIZER
# =========================================================

class WishListSerializer(serializers.ModelSerializer):

    product_name = serializers.CharField(
        source="product.name",
        read_only=True
    )

    product_slug = serializers.CharField(
        source="product.slug",
        read_only=True
    )

    product_image = serializers.ImageField(
        source="product.image",
        read_only=True
    )

    class Meta:
        model = WishList

        fields = [
            "id",
            "slug",
            "product",
            "product_name",
            "product_slug",
            "product_image",
            "created_at",
        ]

        read_only_fields = [
            "id",
            "slug",
            "product_name",
            "product_slug",
            "product_image",
            "created_at",
        ]