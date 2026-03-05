from __future__ import annotations

from django.test import SimpleTestCase, tag

from apps.common.exceptions import (
    _extract_first_error_message,
    _normalize_error_message,
)


@tag("unit")
class ExceptionHandlerUnitTests(SimpleTestCase):
    def test_extract_first_error_message_from_nested_payload(self) -> None:
        detail = {
            "title": ["标题不能为空"],
            "meta": {
                "tags": ["标签格式错误"],
            },
        }
        self.assertEqual(_extract_first_error_message(detail), "标题不能为空")

    def test_normalize_default_messages(self) -> None:
        self.assertEqual(_normalize_error_message("Not found."), "资源不存在")
        self.assertEqual(_normalize_error_message(""), "请求处理失败")
        self.assertEqual(_normalize_error_message("Method \"GET\" not allowed."), "请求方法不被允许")
