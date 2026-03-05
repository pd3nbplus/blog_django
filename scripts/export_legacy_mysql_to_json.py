"""导出旧 MySQL 数据到 JSON 文件。

用途：
1) 在 Windows 主机执行（可访问 Windows 本机 127.0.0.1:3306）。
2) 导出迁移所需表：backmanage_customuser / article_category / article_post / article_comment。
3) 可选读取文章 markdown 文件内容（根据 md_path），写入 article_post.resolved_markdown 字段。

示例：
    python export_legacy_mysql_to_json.py --output legacy_export.json
    python export_legacy_mysql_to_json.py --host 127.0.0.1 --port 3306 --user root --password xxx
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any

import pymysql
from pymysql.cursors import DictCursor

REQUIRED_TABLES = (
    "backmanage_customuser",
    "article_category",
    "article_post",
    "article_comment",
)


TABLE_SQL = {
    "backmanage_customuser": """
        SELECT id, username, first_name, last_name, email, password,
               is_staff, is_active, is_superuser, last_login, date_joined
        FROM backmanage_customuser
        ORDER BY id ASC
    """,
    "article_category": """
        SELECT id, name, level, parent_id, img_path
        FROM article_category
        ORDER BY id ASC
    """,
    "article_post": """
        SELECT id, title, content, abstract, md_path, img_path,
               author_id, category_id, status, view_count,
               created_at, updated_at
        FROM article_post
        ORDER BY id ASC
    """,
    "article_comment": """
        SELECT id, post_id, author_name, author_email, content, created_at
        FROM article_comment
        ORDER BY id ASC
    """,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export legacy MySQL data to JSON")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3306)
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default="mysql2002")
    parser.add_argument("--database", default="blog_project")
    parser.add_argument("--output", default="legacy_export.json", help="导出 JSON 路径")
    parser.add_argument("--indent", type=int, default=2)
    parser.add_argument(
        "--legacy-media-root",
        default="",
        help="旧项目 static/temp 根目录（可选，用于从 md_path 读取 markdown）",
    )
    parser.add_argument(
        "--article-temp-root",
        default="",
        help="旧项目 static/temp 根目录（可选，用于从 md_path 读取 markdown）",
    )
    return parser.parse_args()


def json_default(value: Any) -> Any:
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
    return value


def resolve_markdown(md_path: str | None, legacy_media_root: Path | None, article_temp_root: Path | None) -> str:
    if not md_path:
        return ""

    normalized = md_path.lstrip("/\\")
    candidates: list[Path] = []
    if legacy_media_root:
        candidates.append(legacy_media_root / normalized)
    if article_temp_root:
        candidates.append(article_temp_root / normalized)

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate.read_text(encoding="utf-8", errors="ignore")
    return ""


def assert_required_tables(conn: pymysql.Connection, database: str) -> None:
    sql = """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = %s
    """
    with conn.cursor() as cursor:
        cursor.execute(sql, (database,))
        existing = {row["table_name"] for row in cursor.fetchall()}

    missing = sorted(set(REQUIRED_TABLES) - existing)
    if missing:
        raise RuntimeError(f"Missing required tables: {', '.join(missing)}")


def main() -> None:
    args = parse_args()
    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    legacy_media_root = Path(args.legacy_media_root).expanduser().resolve() if args.legacy_media_root else None
    article_temp_root = Path(args.article_temp_root).expanduser().resolve() if args.article_temp_root else None

    conn = pymysql.connect(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.database,
        charset="utf8mb4",
        cursorclass=DictCursor,
    )

    try:
        assert_required_tables(conn, args.database)

        tables: dict[str, list[dict[str, Any]]] = {}
        counts: dict[str, int] = {}
        with conn.cursor() as cursor:
            for table_name in REQUIRED_TABLES:
                cursor.execute(TABLE_SQL[table_name])
                rows: list[dict[str, Any]] = cursor.fetchall()

                if table_name == "article_post":
                    for row in rows:
                        row["resolved_markdown"] = resolve_markdown(
                            row.get("md_path"),
                            legacy_media_root=legacy_media_root,
                            article_temp_root=article_temp_root,
                        )

                tables[table_name] = rows
                counts[table_name] = len(rows)

        payload = {
            "meta": {
                "exported_at": datetime.now().isoformat(),
                "database": args.database,
                "host": args.host,
                "port": args.port,
                "table_counts": counts,
            },
            "tables": tables,
        }

        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=args.indent, default=json_default),
            encoding="utf-8",
        )

        print(f"Exported JSON: {output_path}")
        for table_name in REQUIRED_TABLES:
            print(f"  - {table_name}: {counts[table_name]}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
