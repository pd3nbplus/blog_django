from __future__ import annotations

import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

from .logging_utils import get_client_ip, get_user_label, truncate_text

error_logger = logging.getLogger("blog_api.error")

DEFAULT_MESSAGE_MAPPING = {
    "Not found.": "资源不存在",
    "Invalid token.": "登录状态无效，请重新登录",
    "Authentication credentials were not provided.": "未提供身份认证信息",
    "Given token not valid for any token type": "登录状态无效，请重新登录",
    "You do not have permission to perform this action.": "没有权限执行当前操作",
}


def _extract_first_error_message(detail):
    if isinstance(detail, dict):
        for value in detail.values():
            message = _extract_first_error_message(value)
            if message:
                return message
        return ""
    if isinstance(detail, list):
        for value in detail:
            message = _extract_first_error_message(value)
            if message:
                return message
        return ""
    return str(detail) if detail is not None else ""


def _normalize_error_message(raw_message: str) -> str:
    message = str(raw_message or "").strip()
    if not message:
        return "请求处理失败"
    if message in DEFAULT_MESSAGE_MAPPING:
        return DEFAULT_MESSAGE_MAPPING[message]
    if message.startswith("Method ") and message.endswith(" not allowed."):
        return "请求方法不被允许"
    if "不被允许" in message and ("方法" in message or "method" in message.lower()):
        return "请求方法不被允许"
    return message


def custom_exception_handler(exc, context):
    request = context.get("request")
    method = getattr(request, "method", "-")
    path = getattr(request, "path", "-")
    user_label = get_user_label(getattr(request, "user", None))
    client_ip = get_client_ip(request) if request is not None else "-"

    response = exception_handler(exc, context)
    if response is None:
        error_logger.error(
            "[error][未捕获异常] 方法=%s 路径=%s 用户=%s 客户端IP=%s 异常类型=%s 异常信息=%s",
            method,
            path,
            user_label,
            client_ip,
            exc.__class__.__name__,
            truncate_text(str(exc) or "-", 200),
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        return Response(
            {"code": status.HTTP_500_INTERNAL_SERVER_ERROR, "message": "服务器内部错误，请稍后重试", "data": None},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    detail = response.data
    if isinstance(detail, dict) and "detail" in detail:
        message = str(detail["detail"])
    else:
        message = _extract_first_error_message(detail) or "请求处理失败"

    status_code = response.status_code
    normalized_message = _normalize_error_message(message)
    detail_preview = truncate_text(str(detail).replace("\n", " "), 240)

    if status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
        error_logger.error(
            "[error][接口异常] 状态码=%s 方法=%s 路径=%s 用户=%s 客户端IP=%s 错误信息=%s 响应明细=%s",
            status_code,
            method,
            path,
            user_label,
            client_ip,
            truncate_text(normalized_message, 160),
            detail_preview,
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        normalized_message = "服务器内部错误，请稍后重试"
    elif status_code >= status.HTTP_400_BAD_REQUEST:
        error_logger.warning(
            "[error][请求异常] 状态码=%s 方法=%s 路径=%s 用户=%s 客户端IP=%s 错误信息=%s 响应明细=%s",
            status_code,
            method,
            path,
            user_label,
            client_ip,
            truncate_text(normalized_message, 160),
            detail_preview,
        )

    response.data = {
        "code": status_code,
        "message": normalized_message,
        "data": detail,
    }
    return response
