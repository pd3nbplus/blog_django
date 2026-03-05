from __future__ import annotations

from django.test import tag
from rest_framework import status
from rest_framework.test import APITestCase


@tag("api")
class ExceptionHandlerApiTests(APITestCase):
    def test_not_authenticated_response_uses_standard_envelope(self) -> None:
        response = self.client.get("/api/v1/auth/profile/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["code"], status.HTTP_401_UNAUTHORIZED)
        self.assertIn("message", response.data)
        self.assertIn("data", response.data)

    def test_method_not_allowed_message_is_normalized(self) -> None:
        response = self.client.get("/api/v1/auth/login/")

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(response.data["code"], status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(response.data["message"], "请求方法不被允许")
