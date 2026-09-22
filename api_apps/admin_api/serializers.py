from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from rest_framework import serializers

User = get_user_model()


# ==============================================================================
# PERMISSION SERIALIZER
# ==============================================================================
class PermissionSerializer(serializers.ModelSerializer):
    """
    Serializes Django's built-in auth Permission model with content_type details.
    """
    app_label = serializers.CharField(source="content_type.app_label", read_only=True)
    model = serializers.CharField(source="content_type.model", read_only=True)

    class Meta:
        model = Permission
        fields = [
            "id",
            "name",
            "codename",
            "app_label",
            "model",
        ]
        read_only_fields = fields


# ==============================================================================
# STAFF USER SERIALIZER
# ==============================================================================
class StaffUserSerializer(serializers.ModelSerializer):
    """
    Serializes a staff member with their assigned user_permissions and summary counts.
    """
    permissions = PermissionSerializer(source="user_permissions", many=True, read_only=True)
    permission_ids = serializers.SerializerMethodField()
    permission_count = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "is_staff",
            "is_superuser",
            "is_active",
            "date_joined",
            "last_login",
            "permission_count",
            "permission_ids",
            "permissions",
        ]
        read_only_fields = fields

    def get_permission_ids(self, obj):
        return list(obj.user_permissions.values_list("id", flat=True))

    def get_permission_count(self, obj):
        return obj.user_permissions.count()


# ==============================================================================
# NON-STAFF USER (CANDIDATE) SERIALIZER
# ==============================================================================
class NonStaffUserSerializer(serializers.ModelSerializer):
    """
    Serializes non-staff users eligible to be promoted to staff.
    """
    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "date_joined",
        ]
        read_only_fields = fields


# ==============================================================================
# STAFF PERMISSIONS UPDATE SERIALIZER
# ==============================================================================
class StaffPermissionsUpdateSerializer(serializers.Serializer):
    """
    Validates payload for updating permissions assigned to a staff user.
    """
    permissions = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        default=list,
        help_text="List of permission IDs to assign to the staff user."
    )

    def validate_permissions(self, value):
        if value:
            existing_count = Permission.objects.filter(id__in=value).count()
            if existing_count != len(set(value)):
                raise serializers.ValidationError("One or more provided permission IDs are invalid.")
        return value


# ==============================================================================
# STAFF ADD / PROMOTE SERIALIZER
# ==============================================================================
class StaffAddSerializer(serializers.Serializer):
    """
    Validates adding a new staff member or promoting an existing user.
    Matches the business logic of admin_panel.views.staff_add.
    """
    action_type = serializers.ChoiceField(
        choices=["existing", "new"],
        default="existing",
        help_text="Either 'existing' to promote a registered user or 'new' to create one."
    )
    # Existing user promotion fields
    user_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="User ID of the existing account to promote."
    )
    # New user creation fields
    username = serializers.CharField(
        max_length=150,
        required=False,
        allow_blank=True,
        help_text="Username for the new staff account."
    )
    email = serializers.EmailField(
        required=False,
        allow_blank=True,
        help_text="Email for the new staff account."
    )
    password = serializers.CharField(
        max_length=128,
        required=False,
        allow_blank=True,
        write_only=True,
        help_text="Password for the new staff account."
    )
    # Permissions list for both cases
    permissions = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        default=list,
        help_text="List of permission IDs to grant to the staff member."
    )

    def validate(self, attrs):
        action_type = attrs.get("action_type", "existing")

        if action_type == "existing":
            user_id = attrs.get("user_id")
            if not user_id:
                raise serializers.ValidationError({"user_id": "Please select an existing user."})
            if not User.objects.filter(id=user_id).exists():
                raise serializers.ValidationError({"user_id": f"User with ID {user_id} does not exist."})

        elif action_type == "new":
            username = attrs.get("username", "").strip()
            email = attrs.get("email", "").strip().lower()
            password = attrs.get("password", "")

            if not username or not email or not password:
                raise serializers.ValidationError(
                    {"detail": "Username, email, and password are required."}
                )

            if User.objects.filter(username__iexact=username).exists():
                raise serializers.ValidationError(
                    {"username": f"Username '{username}' is already taken."}
                )

            if User.objects.filter(email__iexact=email).exists():
                raise serializers.ValidationError(
                    {"email": f"Email '{email}' is already in use."}
                )

        perm_ids = attrs.get("permissions", [])
        if perm_ids:
            existing_count = Permission.objects.filter(id__in=perm_ids).count()
            if existing_count != len(set(perm_ids)):
                raise serializers.ValidationError({"permissions": "One or more permission IDs are invalid."})

        return attrs
