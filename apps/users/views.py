import logging
import math
from pathlib import Path

from django.conf import settings
from django.contrib.auth import logout
from django.core.cache import cache
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.views import APIView

from apps.common.logging_utils import (
    LOG_LEVELS,
    get_client_ip,
    get_user_label,
    read_log_entries,
    truncate_text,
)
from apps.common.responses import error_response, success_response
from apps.common.serializers import EmptySerializer

from .serializers import (
    AdminPasswordUpdateSerializer,
    AdminProfileUpdateSerializer,
    LoginSerializer,
    UserProfileSerializer,
)

audit_logger = logging.getLogger("blog_api.audit")


class LoginAPIView(APIView):
    serializer_class = EmptySerializer
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        username = str(request.data.get("username") or "").strip()
        client_ip = get_client_ip(request)
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as exc:
            audit_logger.warning(
                "[audit][登录失败] 用户名=%s 客户端IP=%s 原因=%s",
                username or "-",
                client_ip,
                truncate_text(str(exc.detail), 200),
            )
            raise

        user = serializer.validated_data["user"]
        token, _ = Token.objects.get_or_create(user=user)
        audit_logger.info(
            "[audit][登录成功] 用户=%s 客户端IP=%s",
            get_user_label(user),
            client_ip,
        )
        return success_response(
            data={
                "token": token.key,
                "user": UserProfileSerializer(user).data,
            }
        )


class LogoutAPIView(APIView):
    serializer_class = EmptySerializer
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user_label = get_user_label(request.user)
        Token.objects.filter(user=request.user).delete()
        logout(request)
        audit_logger.info("[audit][退出登录] 用户=%s 客户端IP=%s", user_label, get_client_ip(request))
        return success_response(message="logout success")


class ProfileAPIView(APIView):
    serializer_class = EmptySerializer
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return success_response(data=UserProfileSerializer(request.user).data)


class AdminProfileAPIView(APIView):
    serializer_class = EmptySerializer
    permission_classes = [IsAdminUser]

    def get(self, request):
        return success_response(data=UserProfileSerializer(request.user).data)

    def patch(self, request):
        serializer = AdminProfileUpdateSerializer(instance=request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        cache.delete_many(["home:summary:v3", "home:summary:v4"])
        updated_fields = ",".join(sorted(serializer.validated_data.keys()))
        audit_logger.info(
            "[audit][管理员资料更新] 用户=%s 更新字段=%s 客户端IP=%s",
            get_user_label(request.user),
            updated_fields or "-",
            get_client_ip(request),
        )
        return success_response(data=UserProfileSerializer(request.user).data, message="updated")


class AdminPasswordAPIView(APIView):
    serializer_class = EmptySerializer
    permission_classes = [IsAdminUser]

    def post(self, request):
        serializer = AdminPasswordUpdateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        Token.objects.filter(user=user).exclude(key=request.auth.key if request.auth else "").delete()
        audit_logger.warning(
            "[audit][管理员密码重置] 用户=%s 客户端IP=%s",
            get_user_label(user),
            get_client_ip(request),
        )
        return success_response(message="password updated")


class AdminLogListAPIView(APIView):
    serializer_class = EmptySerializer
    permission_classes = [IsAdminUser]

    def get(self, request):
        page_raw = request.query_params.get("page", 1)
        page_size_raw = request.query_params.get("page_size", 20)
        level_raw = str(request.query_params.get("level") or "").strip().upper()
        keyword = str(request.query_params.get("q") or "").strip().lower()
        source_filter = str(request.query_params.get("source") or "all").strip().lower()

        try:
            page = max(int(page_raw), 1)
        except (TypeError, ValueError):
            page = 1

        try:
            page_size = int(page_size_raw)
        except (TypeError, ValueError):
            page_size = 20
        page_size = min(max(page_size, 1), 100)

        if level_raw and level_raw not in LOG_LEVELS:
            return error_response(message=f"level 参数无效，支持：{', '.join(LOG_LEVELS)}", code=400)

        log_dir = Path(getattr(settings, "LOG_DIR", settings.BASE_DIR / "logs"))
        entries = read_log_entries(log_dir=log_dir)

        if level_raw:
            entries = [item for item in entries if item.get("level") == level_raw]

        if source_filter in {"audit", "application", "django"}:
            entries = [item for item in entries if item.get("source") == source_filter]

        if keyword:
            entries = [
                item
                for item in entries
                if keyword in item.get("message", "").lower() or keyword in item.get("location", "").lower()
            ]

        count = len(entries)
        num_pages = max(1, math.ceil(count / page_size)) if count else 1
        if page > num_pages:
            page = num_pages
        start = (page - 1) * page_size
        end = start + page_size
        page_items = entries[start:end]

        level_counts = {name: 0 for name in LOG_LEVELS}
        for item in entries:
            level = item.get("level")
            if level in level_counts:
                level_counts[level] += 1

        return success_response(
            data={
                "count": count,
                "page": page,
                "page_size": page_size,
                "num_pages": num_pages,
                "level_counts": level_counts,
                "results": page_items,
            }
        )
