from __future__ import annotations

import re
from collections import deque
from datetime import datetime
from pathlib import Path

LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
LOG_LINE_PATTERN = re.compile(
    r"^\[(?P<level>[A-Z]+)\]\[(?P<timestamp>[^\]]+)\]\[(?P<location>[^\]]+)\]\s?(?P<message>.*)$"
)


def get_client_ip(request) -> str:
    forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = (request.META.get("HTTP_X_REAL_IP") or "").strip()
    if real_ip:
        return real_ip
    return (request.META.get("REMOTE_ADDR") or "").strip() or "-"


def get_user_label(user) -> str:
    if not getattr(user, "is_authenticated", False):
        return "anonymous"
    username = getattr(user, "username", "unknown")
    user_id = getattr(user, "id", "-")
    return f"{username}#{user_id}"


def truncate_text(value: str, limit: int = 180) -> str:
    if len(value) <= limit:
        return value
    if limit <= 3:
        return value[:limit]
    return f"{value[: limit - 3]}..."


def _candidate_log_files(log_dir: Path, include_rotated: bool = True) -> list[Path]:
    files: list[Path] = []
    current = log_dir / "blog_api.log"
    if current.exists() and current.is_file():
        files.append(current)
    if include_rotated:
        rotated = sorted(
            [path for path in log_dir.glob("blog_api.log.*") if path.is_file()],
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        files.extend(rotated[:2])
    return files


def _tail_lines(file_path: Path, limit: int) -> list[str]:
    with file_path.open("r", encoding="utf-8", errors="ignore") as fp:
        return list(deque(fp, maxlen=max(1, limit)))


def _guess_source(message: str, location: str) -> str:
    if "[audit]" in message:
        return "audit"
    if "basehttp.py" in location or "wsgi.py" in location:
        return "django"
    return "application"


def _parse_time(value: str):
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S,%f")
    except ValueError:
        return None


def read_log_entries(
    *,
    log_dir: Path,
    include_rotated: bool = True,
    max_lines_per_file: int = 3000,
) -> list[dict]:
    entries: list[dict] = []
    for file_path in _candidate_log_files(log_dir, include_rotated=include_rotated):
        lines = _tail_lines(file_path, max_lines_per_file)
        current = None
        for line in lines:
            text = line.rstrip("\n")
            matched = LOG_LINE_PATTERN.match(text)
            if matched:
                current = {
                    "id": f"{file_path.name}:{len(entries) + 1}",
                    "level": matched.group("level"),
                    "timestamp": matched.group("timestamp"),
                    "location": matched.group("location"),
                    "message": matched.group("message"),
                    "source": _guess_source(matched.group("message"), matched.group("location")),
                    "file": file_path.name,
                }
                entries.append(current)
                continue

            if current is not None and text.strip():
                current["message"] = f"{current['message']}\n{text}"

    entries.sort(
        key=lambda item: (_parse_time(item["timestamp"]) or datetime.min, item["id"]),
        reverse=True,
    )
    return entries
