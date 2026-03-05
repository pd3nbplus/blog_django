"""初始化 MySQL8 数据库（utf8mb4）。

示例:
    python scripts/setup_mysql8.py
"""

from __future__ import annotations

import os

try:
    import pymysql
except ImportError as exc:  # pragma: no cover
    raise SystemExit("请先安装 pymysql: pip install pymysql") from exc


def main() -> None:
    host = os.getenv("DB_HOST", "127.0.0.1")
    port = int(os.getenv("DB_PORT", "3307"))
    user = os.getenv("DB_USER", "root")
    password = os.getenv("DB_PASSWORD", "ubuntu2002")
    db_name = os.getenv("DB_NAME", "blog_project")

    conn = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.Cursor,
        autocommit=True,
    )
    with conn.cursor() as cursor:
        cursor.execute(
            f"CREATE DATABASE IF NOT EXISTS `{db_name}` DEFAULT CHARACTER SET utf8mb4 DEFAULT COLLATE utf8mb4_unicode_ci"
        )
    conn.close()
    print(f"database `{db_name}` ensured at {host}:{port}")


if __name__ == "__main__":
    main()
