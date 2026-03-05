from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.articles.models import Article, Category, Comment
from apps.articles.services import normalize_source_markdown_path, strip_html_to_text

try:
    import pymysql
except ImportError:  # pragma: no cover
    pymysql = None


class Command(BaseCommand):
    help = "从旧 MySQL5.7 库迁移非 HTML 数据，并从 md 文件加载 markdown 内容"

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true", help="导入前清空当前新表数据")
        parser.add_argument("--host", default="127.0.0.1", help="旧库数据库主机")
        parser.add_argument("--port", type=int, default=3306, help="旧库数据库端口")
        parser.add_argument("--user", default="root", help="旧库数据库用户名")
        parser.add_argument("--password", default="mysql2002", help="旧库数据库密码")
        parser.add_argument("--database", default="blog_project", help="旧库数据库名")
        parser.add_argument(
            "--legacy-media-root",
            default=str(Path(settings.BASE_DIR) / "static" / "temp"),
            help="旧项目静态目录根路径（用于按 md_path 读取 markdown）",
        )
        parser.add_argument(
            "--article-temp-root",
            default=str(Path(settings.BASE_DIR) / "static" / "temp"),
            help="项目内静态目录根路径（用于按 md_path 读取 markdown）",
        )

    def handle(self, *args, **options):
        if pymysql is None:
            raise CommandError("未安装 pymysql，请先安装: pip install pymysql")

        cfg = {
            "host": options["host"],
            "port": options["port"],
            "user": options["user"],
            "password": options["password"],
            "database": options["database"],
            "charset": "utf8mb4",
            "cursorclass": pymysql.cursors.DictCursor,
        }

        legacy_media_root = Path(options["legacy_media_root"]).expanduser().resolve()
        article_temp_root = Path(options["article_temp_root"]).expanduser().resolve()

        self.stdout.write(self.style.WARNING(f"legacy db: {cfg['host']}:{cfg['port']}/{cfg['database']}"))

        with pymysql.connect(**cfg) as conn:
            with conn.cursor() as cursor, transaction.atomic():
                if options["clear"]:
                    self.stdout.write(self.style.WARNING("清空新库数据..."))
                    Comment.objects.all().delete()
                    Article.objects.all().delete()
                    Category.objects.all().delete()

                self._import_users(cursor)
                self._import_categories(cursor)
                self._import_articles(cursor, legacy_media_root, article_temp_root)
                self._import_comments(cursor)

        self.stdout.write(self.style.SUCCESS("导入完成"))

    def _import_users(self, cursor):
        cursor.execute(
            """
            SELECT id, username, first_name, last_name, email, password,
                   is_staff, is_active, is_superuser, last_login, date_joined
            FROM backmanage_customuser
            ORDER BY id ASC
            """
        )
        rows = cursor.fetchall()

        created = 0
        for row in rows:
            user, was_created = User.objects.update_or_create(
                id=row["id"],
                defaults={
                    "username": row["username"] or f"legacy_user_{row['id']}",
                    "first_name": row.get("first_name") or "",
                    "last_name": row.get("last_name") or "",
                    "email": row.get("email") or "",
                    "password": row.get("password") or "",
                    "is_staff": bool(row.get("is_staff")),
                    "is_active": bool(row.get("is_active", True)),
                    "is_superuser": bool(row.get("is_superuser")),
                    "last_login": row.get("last_login"),
                    "date_joined": row.get("date_joined") or timezone.now(),
                },
            )
            if was_created:
                created += 1
        self.stdout.write(f"users imported: {len(rows)} (created {created})")

    def _import_categories(self, cursor):
        cursor.execute(
            """
            SELECT id, name, level, parent_id, img_path
            FROM article_category
            ORDER BY id ASC
            """
        )
        rows = cursor.fetchall()

        # 先创建不含 parent 的节点，再二次回填 parent
        category_map = {}
        for row in rows:
            category, _ = Category.objects.update_or_create(
                id=row["id"],
                defaults={
                    "name": row["name"],
                    "level": row.get("level") or 1,
                    "icon_path": row.get("img_path") or "",
                    "order": row["id"],
                },
            )
            category_map[row["id"]] = (category, row.get("parent_id"))

        for _cid, (category, parent_id) in category_map.items():
            if parent_id and parent_id in category_map:
                category.parent_id = parent_id
                category.save(update_fields=["parent", "updated_at"])

        self.stdout.write(f"categories imported: {len(rows)}")

    def _import_articles(self, cursor, legacy_media_root: Path, article_temp_root: Path):
        cursor.execute(
            """
            SELECT id, title, content, abstract, md_path, img_path,
                   author_id, category_id, status, view_count,
                   created_at, updated_at
            FROM article_post
            ORDER BY id ASC
            """
        )
        rows = cursor.fetchall()

        imported = 0
        for row in rows:
            markdown_content = self._load_markdown(row.get("md_path"), legacy_media_root, article_temp_root)
            if not markdown_content:
                markdown_content = strip_html_to_text(row.get("content") or "")

            if not markdown_content:
                # 最后一层兜底，避免空内容导致校验失败
                markdown_content = "# 无标题\n\n历史文章缺少可用 Markdown 内容。"

            author_id = row.get("author_id")
            if not User.objects.filter(id=author_id).exists():
                continue

            category_id = row.get("category_id")
            if category_id and not Category.objects.filter(id=category_id).exists():
                category_id = None

            article, _ = Article.objects.update_or_create(
                id=row["id"],
                defaults={
                    "legacy_post_id": row["id"],
                    "title": row["title"] or f"legacy-article-{row['id']}",
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
                    "created_at": row.get("created_at") or timezone.now(),
                    "updated_at": row.get("updated_at") or timezone.now(),
                },
            )
            if article.status == Article.Status.PUBLISHED and not article.published_at:
                article.published_at = article.created_at
                article.save(update_fields=["published_at", "updated_at"])

            imported += 1

        self.stdout.write(f"articles imported: {imported}")

    def _import_comments(self, cursor):
        cursor.execute(
            """
            SELECT id, post_id, author_name, author_email, content, created_at
            FROM article_comment
            ORDER BY id ASC
            """
        )
        rows = cursor.fetchall()

        imported = 0
        for row in rows:
            if not Article.objects.filter(id=row["post_id"]).exists():
                continue
            Comment.objects.update_or_create(
                id=row["id"],
                defaults={
                    "article_id": row["post_id"],
                    "author_name": row.get("author_name") or "匿名",
                    "author_email": row.get("author_email") or "anonymous@example.com",
                    "content": row.get("content") or "",
                    "is_approved": True,
                    "created_at": row.get("created_at") or timezone.now(),
                },
            )
            imported += 1

        self.stdout.write(f"comments imported: {imported}")

    def _load_markdown(self, md_path: str, legacy_media_root: Path, article_temp_root: Path) -> str:
        if md_path:
            normalized = md_path.lstrip("/\\")
            candidates = [
                legacy_media_root / normalized,
                article_temp_root / normalized,
                Path(settings.BASE_DIR) / normalized,
            ]
            for path in candidates:
                if path.exists() and path.is_file():
                    return path.read_text(encoding="utf-8", errors="ignore")

        # md_path 为空时，无法可靠映射，不做全盘模糊扫描避免误匹配
        return ""
