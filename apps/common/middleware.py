from __future__ import annotations

import logging
import time
import uuid

from .logging_utils import get_client_ip, get_user_label, truncate_text

audit_logger = logging.getLogger("blog_api.audit")


class ApiAuditLogMiddleware:
    """Audit admin/auth API operations and failed requests for operations staff."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith("/api/v1/"):
            return self.get_response(request)

        request_id = uuid.uuid4().hex[:12]
        started_at = time.perf_counter()

        try:
            response = self.get_response(request)
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            self._log_exception(request, request_id, elapsed_ms, exc)
            raise

        try:
            response["X-Request-ID"] = request_id
        except Exception:
            pass

        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        self._log_response(request, response, response.status_code, request_id, elapsed_ms)
        return response

    @staticmethod
    def _is_focus_path(path: str) -> bool:
        return path.startswith("/api/v1/admin/") or path.startswith("/api/v1/auth/")

    @staticmethod
    def _extract_first_error_message(detail) -> str:
        if isinstance(detail, dict):
            for value in detail.values():
                message = ApiAuditLogMiddleware._extract_first_error_message(value)
                if message:
                    return message
            return ""
        if isinstance(detail, list):
            for value in detail:
                message = ApiAuditLogMiddleware._extract_first_error_message(value)
                if message:
                    return message
            return ""
        return str(detail) if detail is not None else ""

    def _extract_response_error_summary(self, response, status_code: int) -> str:
        if status_code < 400:
            return "-"

        if response is None:
            return "-"

        detail = getattr(response, "data", None)
        if detail is None:
            content = getattr(response, "content", b"")
            if isinstance(content, bytes | bytearray):
                message = content.decode("utf-8", errors="ignore").strip()
            else:
                message = str(content).strip()
            if not message:
                return "-"
            return truncate_text(message.replace("\n", " "), 200)

        if isinstance(detail, dict):
            if "message" in detail and detail["message"] is not None:
                message = str(detail["message"])
            elif "detail" in detail and detail["detail"] is not None:
                message = str(detail["detail"])
            else:
                message = self._extract_first_error_message(detail)
        else:
            message = self._extract_first_error_message(detail)

        message = message.replace("\n", " ").strip()
        if not message:
            return "-"
        return truncate_text(message, 200)

    def _log_response(self, request, response, status_code: int, request_id: str, elapsed_ms: int) -> None:
        if status_code < 400 and not self._is_focus_path(request.path):
            return

        query_string = (request.META.get("QUERY_STRING") or "").strip()
        query_suffix = f"?{truncate_text(query_string, 240)}" if query_string else ""
        user_label = get_user_label(request.user)
        ip = get_client_ip(request)
        ua = truncate_text((request.META.get("HTTP_USER_AGENT") or "-").strip(), 120)
        error_summary = self._extract_response_error_summary(response, status_code)

        message = (
            "[audit][接口请求] 请求ID=%s 用户=%s 方法=%s 路径=%s%s 状态码=%s 耗时毫秒=%s 客户端IP=%s UA=%s 错误摘要=%s"
        )
        args = (
            request_id,
            user_label,
            request.method,
            request.path,
            query_suffix,
            status_code,
            elapsed_ms,
            ip,
            ua,
            error_summary,
        )

        if status_code >= 500:
            audit_logger.error(message, *args)
        elif status_code >= 400:
            audit_logger.warning(message, *args)
        else:
            audit_logger.info(message, *args)

    def _log_exception(self, request, request_id: str, elapsed_ms: int, exc: Exception) -> None:
        query_string = (request.META.get("QUERY_STRING") or "").strip()
        query_suffix = f"?{truncate_text(query_string, 240)}" if query_string else ""
        user_label = get_user_label(request.user)
        ip = get_client_ip(request)
        ua = truncate_text((request.META.get("HTTP_USER_AGENT") or "-").strip(), 120)

        audit_logger.exception(
            "[audit][接口异常] 请求ID=%s 用户=%s 方法=%s 路径=%s%s 耗时毫秒=%s 客户端IP=%s UA=%s 异常类型=%s 异常信息=%s",
            request_id,
            user_label,
            request.method,
            request.path,
            query_suffix,
            elapsed_ms,
            ip,
            ua,
            exc.__class__.__name__,
            truncate_text(str(exc) or "-", 200),
        )
