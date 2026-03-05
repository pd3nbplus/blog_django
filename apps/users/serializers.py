from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import UserSiteSettings


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = authenticate(username=attrs["username"], password=attrs["password"])
        if not user:
            raise serializers.ValidationError("用户名或密码错误")
        if not user.is_active:
            raise serializers.ValidationError("账号已禁用")
        attrs["user"] = user
        return attrs


class UserProfileSerializer(serializers.ModelSerializer):
    home_avatar_path = serializers.SerializerMethodField()
    home_hero_path = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "is_staff",
            "is_superuser",
            "date_joined",
            "last_login",
            "home_avatar_path",
            "home_hero_path",
        ]

    def get_home_avatar_path(self, obj):
        settings = getattr(obj, "site_settings", None)
        return settings.home_avatar_path if settings else ""

    def get_home_hero_path(self, obj):
        settings = getattr(obj, "site_settings", None)
        return settings.home_hero_path if settings else ""


class AdminProfileUpdateSerializer(serializers.ModelSerializer):
    home_avatar_path = serializers.CharField(required=False, allow_blank=True, max_length=255)
    home_hero_path = serializers.CharField(required=False, allow_blank=True, max_length=255)

    class Meta:
        model = User
        fields = ["username", "email", "home_avatar_path", "home_hero_path"]

    def validate_username(self, value):
        username = (value or "").strip()
        if not username:
            raise serializers.ValidationError("用户名不能为空")
        queryset = User.objects.filter(username=username)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("用户名已存在")
        return username

    def validate_home_avatar_path(self, value):
        return (value or "").strip()

    def validate_home_hero_path(self, value):
        return (value or "").strip()

    def update(self, instance, validated_data):
        home_avatar_path = validated_data.pop("home_avatar_path", None)
        home_hero_path = validated_data.pop("home_hero_path", None)
        instance = super().update(instance, validated_data)

        if home_avatar_path is None and home_hero_path is None:
            return instance

        settings, _ = UserSiteSettings.objects.get_or_create(user=instance)
        if home_avatar_path is not None:
            settings.home_avatar_path = home_avatar_path
        if home_hero_path is not None:
            settings.home_hero_path = home_hero_path
        settings.save(update_fields=["home_avatar_path", "home_hero_path", "updated_at"])
        return instance


class AdminPasswordUpdateSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        current_password = attrs.get("current_password") or ""
        new_password = attrs.get("new_password") or ""

        if user is None or not user.check_password(current_password):
            raise serializers.ValidationError("当前密码错误")

        validate_password(new_password, user=user)
        attrs["user"] = user
        return attrs
