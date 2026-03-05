from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.text import slugify

from apps.articles.models import Article, Category, Comment
from apps.articles.services import html_to_markdown, normalize_source_markdown_path


class Command(BaseCommand):
    help = "从 legacy_export.json 导入旧系统数据"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--clear", action="store_true", help="导入前清空当前新表数据")
        parser.add_argument(
            "--file",
            default=str(Path(settings.BASE_DIR) / "data" / "legacy" / "legacy_export.json"),
            help="导出 JSON 文件路径",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        json_file = Path(options["file"]).expanduser()
        if not json_file.exists():
            raise CommandError(f"JSON 文件不存在: {json_file}")

        try:
            payload = json.loads(json_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CommandError(f"JSON 解析失败: {exc}") from exc

        tables = payload.get("tables") or {}
        required_tables = {"backmanage_customuser", "article_category", "article_post", "article_comment"}
        missing = sorted(required_tables - set(tables.keys()))
        if missing:
            raise CommandError(f"JSON 缺少必要表: {', '.join(missing)}")

        with transaction.atomic():
            if options.get("clear"):
                self.stdout.write(self.style.WARNING("清空新库数据..."))
                Comment.objects.all().delete()
                Article.objects.all().delete()
                Category.objects.all().delete()

            self._import_users(tables["backmanage_customuser"])
            self._import_categories(tables["article_category"])
            self._import_articles(tables["article_post"])
            self._import_comments(tables["article_comment"])

        self.stdout.write(self.style.SUCCESS(f"导入完成: {json_file}"))

    def _import_users(self, rows: list[dict[str, Any]]) -> None:
        created = 0
        for row in rows:
            _, was_created = User.objects.update_or_create(
                id=row["id"],
                defaults={
                    "username": row.get("username") or f"legacy_user_{row['id']}",
                    "first_name": row.get("first_name") or "",
                    "last_name": row.get("last_name") or "",
                    "email": row.get("email") or "",
                    "password": row.get("password") or "",
                    "is_staff": bool(row.get("is_staff")),
                    "is_active": bool(row.get("is_active", True)),
                    "is_superuser": bool(row.get("is_superuser")),
                    "last_login": self._to_datetime(row.get("last_login")),
                    "date_joined": self._to_datetime(row.get("date_joined")) or timezone.now(),
                },
            )
            if was_created:
                created += 1
        self.stdout.write(f"users imported: {len(rows)} (created {created})")

    def _import_categories(self, rows: list[dict[str, Any]]) -> None:
        category_map: dict[int, tuple[Category, int | None]] = {}
        for row in rows:
            category, _ = Category.objects.update_or_create(
                id=row["id"],
                defaults={
                    "name": row.get("name") or f"legacy-category-{row['id']}",
                    "slug": self._build_category_slug(row),
                    "level": row.get("level") or 1,
                    "icon_path": row.get("img_path") or "",
                    "order": row["id"],
                },
            )
            category_map[row["id"]] = (category, row.get("parent_id"))

        for _, (category, parent_id) in category_map.items():
            if parent_id and parent_id in category_map:
                category.parent_id = parent_id
                category.save(update_fields=["parent", "updated_at"])

        self.stdout.write(f"categories imported: {len(rows)}")

    def _import_articles(self, rows: list[dict[str, Any]]) -> None:
        imported = 0
        html_converted = 0
        for row in rows:
            markdown_content = (row.get("resolved_markdown") or "").strip()
            if not markdown_content:
                markdown_content = html_to_markdown(row.get("content") or "")
                if markdown_content:
                    html_converted += 1
            if not markdown_content:
                markdown_content = "# 无标题\n\n历史文章缺少可用 Markdown 内容。"

            author_id = row.get("author_id")
            if author_id is None or not User.objects.filter(id=author_id).exists():
                continue

            category_id = row.get("category_id")
            if category_id and not Category.objects.filter(id=category_id).exists():
                category_id = None

            created_at = self._to_datetime(row.get("created_at")) or timezone.now()
            updated_at = self._to_datetime(row.get("updated_at")) or timezone.now()

            article, _ = Article.objects.update_or_create(
                id=row["id"],
                defaults={
                    "legacy_post_id": row["id"],
                    "title": row.get("title") or f"legacy-article-{row['id']}",
                    "slug": self._build_article_slug(row),
                    "summary": row.get("abstract") or "",
                    "markdown_content": markdown_content,
                    "source_markdown_path": normalize_source_markdown_path(
                        row.get("md_path") or "",
                        reject_deprecated_media_root=False,
                    ),
                    "cover_path": row.get("img_path") or "",
                    "author_id": author_id,
                    "category_id": category_id,
                    "status": row.get("status") or Article.Status.DRAFT,
                    "view_count": row.get("view_count") or 0,
                    "created_at": created_at,
                    "updated_at": updated_at,
                },
            )
            if article.status == Article.Status.PUBLISHED and not article.published_at:
                article.published_at = created_at
                article.save(update_fields=["published_at", "updated_at"])
            imported += 1

        self.stdout.write(f"articles imported: {imported} (html->markdown converted: {html_converted})")

    def _import_comments(self, rows: list[dict[str, Any]]) -> None:
        imported = 0
        for row in rows:
            post_id = row.get("post_id")
            if post_id is None or not Article.objects.filter(id=post_id).exists():
                continue

            Comment.objects.update_or_create(
                id=row["id"],
                defaults={
                    "article_id": post_id,
                    "author_name": row.get("author_name") or "匿名",
                    "author_email": row.get("author_email") or "anonymous@example.com",
                    "content": row.get("content") or "",
                    "is_approved": True,
                    "created_at": self._to_datetime(row.get("created_at")) or timezone.now(),
                },
            )
            imported += 1

        self.stdout.write(f"comments imported: {imported}")

    def _to_datetime(self, value: Any) -> Any:
        if value is None:
            return None
        if hasattr(value, "tzinfo"):
            if timezone.is_naive(value):
                return timezone.make_aware(value, timezone.get_current_timezone())
            return value
        if isinstance(value, str):
            dt = parse_datetime(value)
            if dt is not None:
                if timezone.is_naive(dt):
                    return timezone.make_aware(dt, timezone.get_current_timezone())
                return dt
        return None

    def _build_category_slug(self, row: dict[str, Any]) -> str:
        seed = slugify(row.get("name") or "")
        return f"{seed}-{row['id']}" if seed else f"legacy-category-{row['id']}"

    def _build_article_slug(self, row: dict[str, Any]) -> str:
        seed = slugify(row.get("title") or "")
        return f"{seed}-{row['id']}" if seed else f"legacy-article-{row['id']}"
