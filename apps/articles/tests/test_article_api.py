from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import tag
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.articles.models import Article, Category, Collection
from apps.articles.views import CATEGORY_TREE_CACHE_KEY, HOME_SUMMARY_CACHE_KEY


def assert_success_envelope(testcase: APITestCase, response, *, status_code: int = status.HTTP_200_OK) -> None:
    testcase.assertEqual(response.status_code, status_code)
    testcase.assertEqual(response.data["code"], 200)
    testcase.assertIn("data", response.data)


@tag("api")
class ArticleAPITestCase(APITestCase):
    def setUp(self) -> None:
        cache.clear()
        user_model = get_user_model()
        self.author = user_model.objects.create_user(username="author", password="pass1234")
        self.admin = user_model.objects.create_superuser(username="admin", email="admin@example.com", password="pass1234")

        self.root_category = Category.objects.create(name="Root", slug="root", level=1)
        self.child_category = Category.objects.create(name="Child", slug="child", level=2, parent=self.root_category)

        self.published_article = Article.objects.create(
            title="Published Article",
            slug="published-article",
            summary="Public summary",
            markdown_content="# Heading\n\nBody",
            author=self.author,
            category=self.child_category,
            status=Article.Status.PUBLISHED,
        )
        self.draft_article = Article.objects.create(
            title="Draft Article",
            slug="draft-article",
            summary="Draft summary",
            markdown_content="draft",
            author=self.author,
            category=self.child_category,
            status=Article.Status.DRAFT,
        )

    def test_public_article_list_only_returns_published_items(self) -> None:
        response = self.client.get("/api/v1/articles/")
        assert_success_envelope(self, response)

        payload = response.data["data"]
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["id"], self.published_article.id)

    def test_public_article_detail_increments_view_count(self) -> None:
        response = self.client.get(f"/api/v1/articles/{self.published_article.id}/")
        assert_success_envelope(self, response)

        self.published_article.refresh_from_db()
        self.assertEqual(self.published_article.view_count, 1)
        self.assertIn("rendered_html", response.data["data"])
        self.assertIn("toc", response.data["data"])

    def test_public_article_list_and_detail_include_read_minutes(self) -> None:
        long_article = Article.objects.create(
            title="Long Read",
            slug="long-read",
            summary="Long summary",
            markdown_content="字" * 301,
            author=self.author,
            category=self.child_category,
            status=Article.Status.PUBLISHED,
        )

        list_response = self.client.get("/api/v1/articles/")
        assert_success_envelope(self, list_response)
        rows = list_response.data["data"]["results"]
        row = next(item for item in rows if item["id"] == long_article.id)
        self.assertEqual(row["read_minutes"], 2)

        detail_response = self.client.get(f"/api/v1/articles/{long_article.id}/")
        assert_success_envelope(self, detail_response)
        self.assertEqual(detail_response.data["data"]["read_minutes"], 2)

    def test_home_summary_returns_category_tree(self) -> None:
        response = self.client.get("/api/v1/home/summary/")
        assert_success_envelope(self, response)

        categories = response.data["data"]["categories"]
        self.assertEqual(len(categories), 1)
        self.assertEqual(categories[0]["id"], self.root_category.id)
        self.assertEqual(categories[0]["children"][0]["id"], self.child_category.id)

    def test_home_summary_returns_at_most_three_pinned_collections(self) -> None:
        for idx in range(4):
            collection = Collection.objects.create(
                name=f"Pinned Collection {idx}",
                slug=f"pinned-collection-{idx}",
                summary="Pinned summary",
                is_pinned=True,
                order=idx,
            )
            collection.articles.add(self.published_article, self.draft_article)

        Collection.objects.create(
            name="Normal Collection",
            slug="normal-collection",
            summary="Normal summary",
            is_pinned=False,
        )

        cache.clear()
        response = self.client.get("/api/v1/home/summary/")
        assert_success_envelope(self, response)

        pinned_collections = response.data["data"]["pinned_collections"]
        self.assertEqual(len(pinned_collections), 3)
        self.assertEqual(
            [item["name"] for item in pinned_collections],
            ["Pinned Collection 0", "Pinned Collection 1", "Pinned Collection 2"],
        )
        self.assertEqual(pinned_collections[0]["article_count"], 2)
        self.assertEqual(pinned_collections[0]["total_views"], 0)

    def test_public_collections_list_and_detail(self) -> None:
        target_collection = Collection.objects.create(
            name="目标合集",
            slug="target-collection",
            summary="目标合集概述",
            cover_path="https://img-blog.csdnimg.cn/direct/example-cover.png#pic_center",
            is_pinned=True,
            order=3,
        )
        target_collection.articles.add(self.published_article, self.draft_article)
        Collection.objects.create(
            name="普通合集",
            slug="normal-collection",
            summary="普通合集概述",
            is_pinned=False,
            order=9,
        )

        list_response = self.client.get("/api/v1/collections/")
        assert_success_envelope(self, list_response)
        self.assertEqual(list_response.data["data"]["count"], 2)
        self.assertEqual(list_response.data["data"]["results"][0]["id"], target_collection.id)
        self.assertEqual(list_response.data["data"]["results"][0]["article_count"], 2)

        detail_response = self.client.get(f"/api/v1/collections/{target_collection.id}/")
        assert_success_envelope(self, detail_response)
        self.assertEqual(detail_response.data["data"]["name"], "目标合集")
        self.assertEqual(detail_response.data["data"]["total_views"], 0)

    def test_public_article_list_supports_collection_filter(self) -> None:
        match_collection = Collection.objects.create(name="匹配合集", slug="match-collection")
        mismatch_collection = Collection.objects.create(name="不匹配合集", slug="mismatch-collection")
        outsider_article = Article.objects.create(
            title="Outside Publish",
            slug="outside-publish",
            summary="summary",
            markdown_content="content",
            author=self.author,
            category=self.child_category,
            status=Article.Status.PUBLISHED,
        )
        match_collection.articles.add(self.published_article, self.draft_article)
        mismatch_collection.articles.add(outsider_article)

        response = self.client.get("/api/v1/articles/", {"collection": match_collection.id})
        assert_success_envelope(self, response)
        payload = response.data["data"]
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["id"], self.published_article.id)

        invalid_response = self.client.get("/api/v1/articles/", {"collection": "invalid"})
        assert_success_envelope(self, invalid_response)
        self.assertEqual(invalid_response.data["data"]["count"], 0)

    def test_home_summary_returns_latest_paper_reading_articles_desc_order_limit_15(self) -> None:
        paper_root = Category.objects.create(name="论文阅读", slug="paper-reading", level=1)
        paper_child = Category.objects.create(name="金融科技", slug="fintech", level=2, parent=paper_root)
        paper_grandchild = Category.objects.create(name="深度论文", slug="deep-paper", level=3, parent=paper_child)
        other_root = Category.objects.create(name="其他分类", slug="other-root", level=1)
        other_child = Category.objects.create(name="杂项", slug="other-child", level=2, parent=other_root)

        now = timezone.now()
        for idx in range(17):
            category = paper_child if idx % 2 == 0 else paper_grandchild
            article = Article.objects.create(
                title=f"Paper Article {idx:02d}",
                slug=f"paper-article-{idx:02d}",
                summary="summary",
                markdown_content="content",
                author=self.author,
                category=category,
                status=Article.Status.PUBLISHED,
            )
            article_time = now - timedelta(hours=17 - idx)
            Article.objects.filter(pk=article.pk).update(created_at=article_time, published_at=article_time)

        non_paper_article = Article.objects.create(
            title="Non Paper Latest",
            slug="non-paper-latest",
            summary="summary",
            markdown_content="content",
            author=self.author,
            category=other_child,
            status=Article.Status.PUBLISHED,
        )
        Article.objects.filter(pk=non_paper_article.pk).update(created_at=now + timedelta(hours=1), published_at=now + timedelta(hours=1))

        cache.clear()
        response = self.client.get("/api/v1/home/summary/")
        assert_success_envelope(self, response)

        latest_articles = response.data["data"]["latest_articles"]
        returned_ids = [item["id"] for item in latest_articles]
        self.assertEqual(len(returned_ids), 15)
        self.assertNotIn(non_paper_article.id, returned_ids)

        expected_ids = list(
            Article.objects.filter(status=Article.Status.PUBLISHED, category_id__in=[paper_root.id, paper_child.id, paper_grandchild.id])
            .order_by("-published_at", "-created_at")
            .values_list("id", flat=True)[:15]
        )
        self.assertEqual(returned_ids, expected_ids)

    def test_home_recommendations_supports_seeded_pagination(self) -> None:
        now = timezone.now()
        for idx in range(24):
            article = Article.objects.create(
                title=f"Recommend {idx:02d}",
                slug=f"recommend-{idx:02d}",
                summary="summary",
                markdown_content="content",
                author=self.author,
                category=self.child_category,
                status=Article.Status.PUBLISHED,
                view_count=idx * 20,
            )
            article_time = now - timedelta(days=idx)
            Article.objects.filter(pk=article.pk).update(created_at=article_time, published_at=article_time)

        page1_response = self.client.get("/api/v1/home/recommendations/")
        assert_success_envelope(self, page1_response)
        page1_data = page1_response.data["data"]
        self.assertEqual(page1_data["page"], 1)
        self.assertEqual(page1_data["page_size"], 8)
        self.assertEqual(len(page1_data["results"]), 8)
        self.assertIn("read_minutes", page1_data["results"][0])
        self.assertTrue(page1_data["has_more"])
        self.assertIn("seed", page1_data)

        page1_ids = [item["id"] for item in page1_data["results"]]

        page1_repeat_response = self.client.get(
            "/api/v1/home/recommendations/",
            {"page": 1, "page_size": 8, "seed": page1_data["seed"]},
        )
        assert_success_envelope(self, page1_repeat_response)
        page1_repeat_ids = [item["id"] for item in page1_repeat_response.data["data"]["results"]]
        self.assertEqual(page1_ids, page1_repeat_ids)

        page2_response = self.client.get(
            "/api/v1/home/recommendations/",
            {"page": 2, "page_size": 8, "seed": page1_data["seed"]},
        )
        assert_success_envelope(self, page2_response)
        page2_data = page2_response.data["data"]
        page2_ids = [item["id"] for item in page2_data["results"]]
        self.assertLessEqual(len(page2_ids), 8)
        self.assertTrue(set(page1_ids).isdisjoint(set(page2_ids)))

    def test_home_recommendations_supports_category_filter(self) -> None:
        now = timezone.now()
        root = Category.objects.create(name="筛选父分类", slug="filter-root", level=1)
        child_a = Category.objects.create(name="筛选子类A", slug="filter-child-a", level=2, parent=root)
        child_b = Category.objects.create(name="筛选子类B", slug="filter-child-b", level=2, parent=root)
        outsider_root = Category.objects.create(name="外部分组", slug="outsider-root", level=1)
        outsider = Category.objects.create(name="外部子类", slug="outsider-child", level=2, parent=outsider_root)

        in_category_ids: list[int] = []
        for idx in range(6):
            article = Article.objects.create(
                title=f"Filter In {idx}",
                slug=f"filter-in-{idx}",
                summary="summary",
                markdown_content="content",
                author=self.author,
                category=child_a if idx % 2 == 0 else child_b,
                status=Article.Status.PUBLISHED,
                view_count=100 + idx,
            )
            article_time = now - timedelta(days=idx)
            Article.objects.filter(pk=article.pk).update(created_at=article_time, published_at=article_time)
            in_category_ids.append(article.id)

        for idx in range(4):
            article = Article.objects.create(
                title=f"Filter Out {idx}",
                slug=f"filter-out-{idx}",
                summary="summary",
                markdown_content="content",
                author=self.author,
                category=outsider,
                status=Article.Status.PUBLISHED,
                view_count=300 + idx,
            )
            article_time = now - timedelta(days=idx)
            Article.objects.filter(pk=article.pk).update(created_at=article_time, published_at=article_time)

        response = self.client.get(
            "/api/v1/home/recommendations/",
            {"category": root.id, "page_size": 20, "seed": 20260304},
        )
        assert_success_envelope(self, response)
        results = response.data["data"]["results"]
        returned_ids = [item["id"] for item in results]

        self.assertEqual(len(returned_ids), len(in_category_ids))
        self.assertTrue(set(returned_ids).issubset(set(in_category_ids)))

    def test_admin_article_endpoints_require_admin_role(self) -> None:
        unauthenticated = self.client.get("/api/v1/admin/articles/")
        self.assertIn(unauthenticated.status_code, {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN})

        self.client.force_authenticate(user=self.author)
        non_admin = self.client.get("/api/v1/admin/articles/")
        self.assertEqual(non_admin.status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(user=None)

        self.client.force_authenticate(user=self.admin)
        create_response = self.client.post(
            "/api/v1/admin/articles/",
            {
                "title": "Admin Created",
                "slug": "admin-created",
                "summary": "summary",
                "markdown_content": "content",
                "category": self.root_category.id,
                "status": Article.Status.DRAFT,
            },
            format="json",
        )
        assert_success_envelope(self, create_response)

        delete_response = self.client.delete(f"/api/v1/admin/articles/{self.published_article.id}/")
        assert_success_envelope(self, delete_response)

        self.assertFalse(Article.objects.filter(id=self.published_article.id).exists())

    def test_admin_upload_markdown_defaults_to_static_temp(self) -> None:
        self.client.force_authenticate(user=self.admin)
        markdown_file = SimpleUploadedFile(
            "new-upload.md",
            b"# Demo\n\ncontent",
            content_type="text/markdown",
        )
        response = self.client.post(
            "/api/v1/admin/articles/upload-markdown/",
            {"markdown_file": markdown_file},
            format="multipart",
        )
        assert_success_envelope(self, response)

        payload = response.data["data"]
        self.assertTrue(payload["source_markdown_path"].startswith("/static/temp/uploads/"))
        saved_to = Path(payload["saved_to"])
        self.assertTrue(saved_to.exists())
        self.assertEqual(saved_to.read_text(encoding="utf-8"), "# Demo\n\ncontent")

        saved_to.unlink(missing_ok=True)

    def test_admin_upload_markdown_rejects_media_articles_root(self) -> None:
        self.client.force_authenticate(user=self.admin)
        markdown_file = SimpleUploadedFile(
            "legacy.md",
            b"# Legacy\n\ncontent",
            content_type="text/markdown",
        )
        response = self.client.post(
            "/api/v1/admin/articles/upload-markdown/",
            {
                "markdown_file": markdown_file,
                "source_markdown_path": "/media/articles/uploads/legacy.md",
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], 400)
        self.assertIn("不再支持 /media/articles", response.data["message"])

    def test_admin_upload_cover_defaults_to_static_temp(self) -> None:
        self.client.force_authenticate(user=self.admin)
        cover_file = SimpleUploadedFile(
            "cover.png",
            b"fake-png-content",
            content_type="image/png",
        )
        response = self.client.post(
            "/api/v1/admin/articles/upload-cover/",
            {"cover_file": cover_file},
            format="multipart",
        )
        assert_success_envelope(self, response)

        payload = response.data["data"]
        self.assertTrue(payload["cover_path"].startswith("/static/temp/uploads/cover/"))
        saved_to = Path(payload["saved_to"])
        self.assertTrue(saved_to.exists())

        saved_to.unlink(missing_ok=True)

    def test_admin_upload_cover_rejects_media_articles_root(self) -> None:
        self.client.force_authenticate(user=self.admin)
        cover_file = SimpleUploadedFile(
            "cover.png",
            b"fake-png-content",
            content_type="image/png",
        )
        response = self.client.post(
            "/api/v1/admin/articles/upload-cover/",
            {
                "cover_file": cover_file,
                "source_markdown_path": "/media/articles/uploads/legacy.md",
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], 400)
        self.assertIn("不再支持 /media/articles", response.data["message"])

    def test_admin_resolve_local_images_is_noop(self) -> None:
        self.client.force_authenticate(user=self.admin)
        unique_name = "skip-physical-upload-20260305.png"
        image_file = SimpleUploadedFile(
            unique_name,
            b"fake-image-bytes",
            content_type="image/png",
        )
        markdown_content = f"![x](./img/{unique_name})"
        response = self.client.post(
            "/api/v1/admin/articles/resolve-local-images/",
            {
                "markdown_content": markdown_content,
                "mappings": json.dumps([{"ref": f"./img/{unique_name}", "file_field": "file_0"}]),
                "file_0": image_file,
            },
            format="multipart",
        )
        assert_success_envelope(self, response)

        payload = response.data["data"]
        self.assertEqual(payload["markdown_content"], markdown_content)
        self.assertEqual(payload["source_markdown_path"], "")
        self.assertEqual(payload["uploaded"], [])
        self.assertEqual(payload["unresolved_refs"], [])

    def test_admin_list_supports_status_and_keyword_filters(self) -> None:
        self.client.force_authenticate(user=self.admin)

        status_response = self.client.get("/api/v1/admin/articles/", {"status": Article.Status.DRAFT})
        assert_success_envelope(self, status_response)
        status_payload = status_response.data["data"]
        self.assertEqual(status_payload["count"], 1)
        self.assertEqual(status_payload["results"][0]["id"], self.draft_article.id)

        keyword_response = self.client.get("/api/v1/admin/articles/", {"q": "published-article"})
        assert_success_envelope(self, keyword_response)
        keyword_payload = keyword_response.data["data"]
        self.assertEqual(keyword_payload["count"], 1)
        self.assertEqual(keyword_payload["results"][0]["id"], self.published_article.id)

    def test_admin_list_supports_category_and_ordering_filters(self) -> None:
        self.client.force_authenticate(user=self.admin)
        another_root = Category.objects.create(name="Another Root", slug="another-root", level=1)
        another_child = Category.objects.create(name="Another Child", slug="another-child", level=2, parent=another_root)
        outsider = Article.objects.create(
            title="Outside Article",
            slug="outside-article",
            summary="summary",
            markdown_content="content",
            author=self.author,
            category=another_child,
            status=Article.Status.PUBLISHED,
            view_count=999,
        )
        self.assertTrue(outsider.id > 0)

        Article.objects.filter(id=self.published_article.id).update(view_count=18)
        Article.objects.filter(id=self.draft_article.id).update(view_count=120)

        by_root_response = self.client.get("/api/v1/admin/articles/", {"category": self.root_category.id})
        assert_success_envelope(self, by_root_response)
        root_ids = [item["id"] for item in by_root_response.data["data"]["results"]]
        self.assertIn(self.published_article.id, root_ids)
        self.assertIn(self.draft_article.id, root_ids)
        self.assertNotIn(outsider.id, root_ids)

        ordered_response = self.client.get("/api/v1/admin/articles/", {"ordering": "-view_count"})
        assert_success_envelope(self, ordered_response)
        ordered_ids = [item["id"] for item in ordered_response.data["data"]["results"]]
        self.assertEqual(ordered_ids[0], outsider.id)

    def test_admin_update_article(self) -> None:
        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(
            f"/api/v1/admin/articles/{self.draft_article.id}/",
            {"title": "Draft Updated", "status": Article.Status.PUBLISHED},
            format="json",
        )
        assert_success_envelope(self, response)

        self.draft_article.refresh_from_db()
        self.assertEqual(self.draft_article.title, "Draft Updated")
        self.assertEqual(self.draft_article.status, Article.Status.PUBLISHED)

    def test_admin_create_duplicate_slug_returns_validation_error(self) -> None:
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            "/api/v1/admin/articles/",
            {
                "title": "Duplicate Slug",
                "slug": self.published_article.slug,
                "summary": "summary",
                "markdown_content": "content",
                "status": Article.Status.DRAFT,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], 400)
        self.assertEqual(response.data["message"], "slug 已存在，请更换")

    def test_admin_collection_crud_and_article_binding(self) -> None:
        self.client.force_authenticate(user=self.admin)

        create_response = self.client.post(
            "/api/v1/admin/collections/",
            {
                "name": "AI合集",
                "slug": "ai-collection",
                "summary": "AI 相关文章",
                "cover_path": "https://img-blog.csdnimg.cn/direct/example-cover.png#pic_center",
                "is_pinned": True,
                "order": 2,
                "article_ids": [self.published_article.id, self.draft_article.id],
            },
            format="json",
        )
        assert_success_envelope(self, create_response)
        collection_id = create_response.data["data"]["id"]
        self.assertEqual(create_response.data["data"]["article_count"], 2)
        self.assertEqual(
            sorted(create_response.data["data"]["article_ids"]),
            sorted([self.published_article.id, self.draft_article.id]),
        )

        list_response = self.client.get("/api/v1/admin/collections/")
        assert_success_envelope(self, list_response)
        self.assertEqual(list_response.data["data"]["count"], 1)

        update_response = self.client.patch(
            f"/api/v1/admin/collections/{collection_id}/",
            {
                "summary": "更新后的合集概述",
                "is_pinned": False,
                "article_ids": [self.published_article.id],
            },
            format="json",
        )
        assert_success_envelope(self, update_response)
        self.assertEqual(update_response.data["data"]["article_count"], 1)
        self.assertFalse(update_response.data["data"]["is_pinned"])

        delete_response = self.client.delete(f"/api/v1/admin/collections/{collection_id}/")
        assert_success_envelope(self, delete_response)
        self.assertFalse(Collection.objects.filter(id=collection_id).exists())

    def test_admin_write_invalidates_public_cache(self) -> None:
        self.client.get("/api/v1/home/summary/")
        self.client.get("/api/v1/categories/tree/")
        self.assertIsNotNone(cache.get(HOME_SUMMARY_CACHE_KEY))
        self.assertIsNotNone(cache.get(CATEGORY_TREE_CACHE_KEY))

        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(
            f"/api/v1/admin/articles/{self.draft_article.id}/",
            {"title": "Cache invalidate"},
            format="json",
        )
        assert_success_envelope(self, response)

        self.assertIsNone(cache.get(HOME_SUMMARY_CACHE_KEY))
        self.assertIsNone(cache.get(CATEGORY_TREE_CACHE_KEY))

    def test_admin_category_create_supports_root_and_child(self) -> None:
        self.client.force_authenticate(user=self.admin)

        root_response = self.client.post(
            "/api/v1/admin/categories/",
            {"name": "Root New"},
            format="multipart",
        )
        assert_success_envelope(self, root_response)
        self.assertIsNone(root_response.data["data"]["parent"])
        self.assertEqual(root_response.data["data"]["level"], 1)

        child_response = self.client.post(
            "/api/v1/admin/categories/",
            {"name": "Child New", "parent": root_response.data["data"]["id"]},
            format="multipart",
        )
        assert_success_envelope(self, child_response)
        self.assertEqual(child_response.data["data"]["parent"], root_response.data["data"]["id"])
        self.assertEqual(child_response.data["data"]["level"], 2)

    @patch("apps.articles.views.urlopen")
    def test_public_image_proxy_supports_csdn_host(self, mocked_urlopen) -> None:
        class _UpstreamHeaders(dict):
            def get_content_type(self):
                return self.get("Content-Type", "application/octet-stream").split(";", 1)[0]

        class _UpstreamResponse:
            def __init__(self, content: bytes, content_type: str):
                self._content = content
                self.headers = _UpstreamHeaders({"Content-Type": content_type, "Content-Length": str(len(content))})

            def read(self, size: int = -1):
                if size < 0:
                    return self._content
                return self._content[:size]

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        mocked_urlopen.return_value = _UpstreamResponse(b"\x89PNG\r\n\x1a\n...", "image/png")
        response = self.client.get(
            "/api/v1/image-proxy/",
            {"url": "https://i-blog.csdnimg.cn/direct/example.png#pic_center"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertIn("Cache-Control", response)
        mocked_urlopen.assert_called_once()

    @patch("apps.articles.views.urlopen")
    def test_public_image_proxy_rejects_non_whitelisted_host(self, mocked_urlopen) -> None:
        response = self.client.get("/api/v1/image-proxy/", {"url": "https://example.com/a.png"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        mocked_urlopen.assert_not_called()

    @patch("apps.articles.views.urlopen")
    def test_public_image_proxy_rejects_non_image_response(self, mocked_urlopen) -> None:
        class _UpstreamHeaders(dict):
            def get_content_type(self):
                return self.get("Content-Type", "application/octet-stream").split(";", 1)[0]

        class _UpstreamResponse:
            def __init__(self):
                self.headers = _UpstreamHeaders({"Content-Type": "text/html", "Content-Length": "18"})

            def read(self, size: int = -1):
                return b"<html>blocked</html>"[:size if size >= 0 else None]

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        mocked_urlopen.return_value = _UpstreamResponse()
        response = self.client.get("/api/v1/image-proxy/", {"url": "https://i-blog.csdnimg.cn/direct/blocked.png"})
        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
