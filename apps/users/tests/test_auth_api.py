from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import tag
from rest_framework import status
from rest_framework.test import APITestCase


def assert_success_envelope(testcase: APITestCase, response) -> None:
    testcase.assertEqual(response.status_code, status.HTTP_200_OK)
    testcase.assertEqual(response.data["code"], 200)
    testcase.assertIn("data", response.data)


@tag("api")
class AuthAPITestCase(APITestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username="test_user", password="pass1234")

    def test_login_profile_logout_flow(self) -> None:
        login_response = self.client.post(
            "/api/v1/auth/login/",
            {"username": "test_user", "password": "pass1234"},
            format="json",
        )
        assert_success_envelope(self, login_response)

        token = login_response.data["data"]["token"]
        self.assertTrue(token)

        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        profile_response = self.client.get("/api/v1/auth/profile/")
        assert_success_envelope(self, profile_response)
        self.assertEqual(profile_response.data["data"]["username"], "test_user")

        logout_response = self.client.post("/api/v1/auth/logout/")
        assert_success_envelope(self, logout_response)

        profile_after_logout = self.client.get("/api/v1/auth/profile/")
        self.assertEqual(profile_after_logout.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_with_wrong_password_returns_error(self) -> None:
        response = self.client.post(
            "/api/v1/auth/login/",
            {"username": "test_user", "password": "wrong-password"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], 400)
