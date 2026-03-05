"""通过 Django 管理命令执行旧库导入（仅导入非 HTML 字段 + Markdown 文件）。

用法：
    python scripts/migrate_legacy_without_html.py [--clear]
"""

from __future__ import annotations

import os
import sys

import django
from django.core.management import call_command


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    django.setup()

    clear = "--clear" in sys.argv
    if clear:
        call_command("import_legacy_data", clear=True)
    else:
        call_command("import_legacy_data")


if __name__ == "__main__":
    main()
