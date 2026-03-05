from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db.models import Q

from apps.articles.models import Article
from apps.articles.services import normalize_source_markdown_path


class Command(BaseCommand):
    help = "将历史 /media/articles source_markdown_path 迁移为 /static/temp"

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="仅预览，不写入数据库",
        )

    def handle(self, *args, **options) -> None:
        dry_run = bool(options.get("dry_run"))

        queryset = Article.objects.filter(
            Q(source_markdown_path__startswith="/media/articles")
            | Q(source_markdown_path__startswith="media/articles")
        ).only("id", "source_markdown_path")

        total = queryset.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS("无需迁移：没有 /media/articles 路径数据"))
            return

        updated = 0
        for article in queryset.iterator(chunk_size=500):
            old_path = article.source_markdown_path or ""
            new_path = normalize_source_markdown_path(
                old_path,
                reject_deprecated_media_root=False,
            )
            if new_path == old_path:
                continue

            updated += 1
            if dry_run:
                self.stdout.write(f"[DRY-RUN] article_id={article.id}: {old_path} -> {new_path}")
                continue

            Article.objects.filter(id=article.id).update(source_markdown_path=new_path)

        if dry_run:
            self.stdout.write(self.style.WARNING(f"预览完成：共命中 {total} 条，待更新 {updated} 条"))
        else:
            self.stdout.write(self.style.SUCCESS(f"迁移完成：共命中 {total} 条，已更新 {updated} 条"))
