from __future__ import annotations

import shutil
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import tag
from rest_framework import status
from rest_framework.test import APITestCase


def assert_success_envelope(testcase: APITestCase, response) -> None:
    testcase.assertEqual(response.status_code, status.HTTP_200_OK)
    testcase.assertEqual(response.data["code"], 200)
    testcase.assertIn("data", response.data)


@tag("api")
class AdminMediaAPITestCase(APITestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.admin = user_model.objects.create_superuser(
            username="media_admin",
            email="media@example.com",
            password="pass1234",
        )
        self.client.force_authenticate(self.admin)

        self.static_root = Path(settings.BASE_DIR) / "static"
        self.test_root = self.static_root / "test-media-api"
        self.test_root.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        if self.test_root.exists():
            shutil.rmtree(self.test_root)
        super().tearDown()

    def test_admin_media_list_returns_static_relative_url(self) -> None:
        file_path = self.test_root / "sample.txt"
        file_path.write_text("demo", encoding="utf-8")

        response = self.client.get("/api/v1/admin/media/", {"path": "test-media-api"})
        assert_success_envelope(self, response)

        payload = response.data["data"]
        self.assertEqual(payload["current_path"], "test-media-api")
        self.assertEqual(len(payload["files"]), 1)
        self.assertEqual(payload["files"][0]["name"], "sample.txt")
        self.assertEqual(payload["files"][0]["url"], "/static/test-media-api/sample.txt")

    def test_admin_media_tree_lists_nested_directories(self) -> None:
        nested = self.test_root / "a" / "b"
        nested.mkdir(parents=True, exist_ok=True)

        response = self.client.get("/api/v1/admin/media/tree/")
        assert_success_envelope(self, response)

        directories = set(response.data["data"]["directories"])
        self.assertIn("test-media-api", directories)
        self.assertIn("test-media-api/a", directories)
        self.assertIn("test-media-api/a/b", directories)

    def test_admin_media_list_can_skip_file_payload(self) -> None:
        child_dir = self.test_root / "child"
        child_dir.mkdir(parents=True, exist_ok=True)
        (self.test_root / "large-image.webp").write_text("mock", encoding="utf-8")

        response = self.client.get(
            "/api/v1/admin/media/",
            {"path": "test-media-api", "include_files": "false"},
        )
        assert_success_envelope(self, response)

        payload = response.data["data"]
        self.assertIn("child", payload["directories"])
        self.assertEqual(payload["files"], [])

    def test_admin_media_upload_rejects_file_larger_than_five_mb(self) -> None:
        large_file = SimpleUploadedFile(
            name="too-large.bin",
            content=b"0" * (5 * 1024 * 1024 + 1),
            content_type="application/octet-stream",
        )

        response = self.client.post(
            "/api/v1/admin/media/upload/",
            {"path": "test-media-api", "file": large_file},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], 400)
        self.assertIn("5MB", response.data["message"])

    def test_admin_media_upload_collection_cover_path_is_normalized(self) -> None:
        upload_file = SimpleUploadedFile(
            name="cover.png",
            content=b"fake-png-content",
            content_type="image/png",
        )

        response = self.client.post(
            "/api/v1/admin/media/upload/",
            {"path": "temp/uploads/collection-cover", "file": upload_file},
            format="multipart",
        )
        assert_success_envelope(self, response)

        payload = response.data["data"]
        self.assertEqual(payload["path"], "temp/collection")
        self.assertTrue(payload["url"].startswith("/static/temp/collection/"))

        saved_file = Path(settings.BASE_DIR) / "static" / payload["path"] / payload["name"]
        self.assertTrue(saved_file.exists())
        saved_file.unlink(missing_ok=True)
