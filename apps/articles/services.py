from __future__ import annotations

import math
import posixpath
import re
from collections.abc import Iterable
from html import unescape
from pathlib import Path

import bleach
import markdown
from django.conf import settings

ALLOWED_TAGS = list(bleach.sanitizer.ALLOWED_TAGS) + [
    "p",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "pre",
    "code",
    "img",
    "blockquote",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "hr",
    "span",
    "div",
]
ALLOWED_ATTRIBUTES = {
    "*": ["class", "id"],
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "title", "loading", "referrerpolicy"],
}
FENCED_CODE_BLOCK_PATTERN = re.compile(r"(```[\s\S]*?```|~~~[\s\S]*?~~~)")
# Support [toc], @[toc], @ [toc], @[ toc ] ... on a standalone line.
TOC_MARKER_PATTERN = re.compile(r"(?im)^[ \t]*@?\s*\[\s*toc\s*\][ \t]*$")
CJK_CHAR_PATTERN = re.compile(r"[\u4e00-\u9fff]")
WORD_PATTERN = re.compile(r"[A-Za-z0-9_]+")
MARKDOWN_IMAGE_PATTERN = re.compile(r"!\[[^\]]*]\([^)\n]+\)")
HTML_IMG_TAG_PATTERN = re.compile(r"<img\b[^>]*>", re.IGNORECASE)


def normalize_toc_markers_outside_codeblocks(markdown_content: str) -> str:
    chunks: list[str] = []
    cursor = 0
    text = markdown_content or ""
    for match in FENCED_CODE_BLOCK_PATTERN.finditer(text):
        start, end = match.span()
        if start > cursor:
            plain = text[cursor:start]
            chunks.append(TOC_MARKER_PATTERN.sub("\n\n[TOC]\n\n", plain))
        chunks.append(text[start:end])
        cursor = end
    if cursor < len(text):
        chunks.append(TOC_MARKER_PATTERN.sub("\n\n[TOC]\n\n", text[cursor:]))
    return "".join(chunks)


def estimate_read_minutes(markdown_content: str) -> int:
    """
    Estimate read time from markdown content using a simple mixed CJK/word count.
    """
    content = markdown_content or ""
    without_code = FENCED_CODE_BLOCK_PATTERN.sub(" ", content)
    markdown_images = MARKDOWN_IMAGE_PATTERN.findall(without_code)
    html_images = HTML_IMG_TAG_PATTERN.findall(without_code)
    image_count = len(markdown_images) + len(html_images)

    text_only_content = MARKDOWN_IMAGE_PATTERN.sub(" ", without_code)
    text_only_content = HTML_IMG_TAG_PATTERN.sub(" ", text_only_content)

    cjk_chars = len(CJK_CHAR_PATTERN.findall(text_only_content))
    words = len(WORD_PATTERN.findall(text_only_content))
    total_units = cjk_chars + words
    text_minutes = total_units / 300 if total_units > 0 else 0
    image_minutes = image_count * 10 / 60
    return max(1, math.ceil(text_minutes + image_minutes))


class MarkdownRenderer:
    @staticmethod
    def render(markdown_content: str) -> tuple[str, str]:
        markdown_content = normalize_toc_markers_outside_codeblocks(markdown_content or "")
        md = markdown.Markdown(
            extensions=[
                "extra",
                "codehilite",
                "tables",
                "toc",
                "fenced_code",
                "nl2br",
            ]
        )
        html = md.convert(markdown_content)
        toc = getattr(md, "toc", "")

        cleaned_html = bleach.clean(
            html,
            tags=ALLOWED_TAGS,
            attributes=ALLOWED_ATTRIBUTES,
            strip=True,
        )
        return cleaned_html, toc


def read_markdown_from_legacy_path(md_path: str) -> str:
    if not md_path:
        return ""

    normalized = md_path.lstrip("/\\")
    candidate_paths = [
        Path(settings.MEDIA_ROOT) / normalized,
        Path(settings.BASE_DIR) / "static" / "temp" / normalized,
    ]
    for path in candidate_paths:
        if path.exists() and path.is_file():
            return path.read_text(encoding="utf-8", errors="ignore")
    return ""


def strip_html_to_text(html: str) -> str:
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", "", html)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _convert_inline_html_to_markdown(html: str) -> str:
    text = html or ""
    text = re.sub(
        r"<a[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
        lambda m: f"[{strip_html_to_text(m.group(2)).strip()}]({m.group(1).strip()})",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(r"<(?:strong|b)>(.*?)</(?:strong|b)>", lambda m: f"**{strip_html_to_text(m.group(1)).strip()}**", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<(?:em|i)>(.*?)</(?:em|i)>", lambda m: f"*{strip_html_to_text(m.group(1)).strip()}*", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<code>(.*?)</code>", lambda m: f"`{strip_html_to_text(m.group(1)).strip()}`", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = strip_html_to_text(text)
    return unescape(text).strip()


def html_to_markdown(html: str) -> str:
    if not html:
        return ""

    content = (html or "").replace("\r\n", "\n")

    def code_block_replacer(match: re.Match[str]) -> str:
        code = unescape(strip_html_to_text(match.group(1))).strip()
        return f"\n```\n{code}\n```\n"

    content = re.sub(
        r"<pre[^>]*>\s*<code[^>]*>([\s\S]*?)</code>\s*</pre>",
        code_block_replacer,
        content,
        flags=re.IGNORECASE,
    )

    for level in range(6, 0, -1):
        def _replace_heading(match: re.Match[str], heading_level: int = level) -> str:
            return f"\n{'#' * heading_level} {_convert_inline_html_to_markdown(match.group(1))}\n"

        content = re.sub(
            rf"<h{level}[^>]*>([\s\S]*?)</h{level}>",
            _replace_heading,
            content,
            flags=re.IGNORECASE,
        )

    content = re.sub(
        r"<li[^>]*>([\s\S]*?)</li>",
        lambda m: f"\n- {_convert_inline_html_to_markdown(m.group(1))}",
        content,
        flags=re.IGNORECASE,
    )
    content = re.sub(r"</?(?:ul|ol)[^>]*>", "\n", content, flags=re.IGNORECASE)
    content = re.sub(
        r"<p[^>]*>([\s\S]*?)</p>",
        lambda m: f"\n{_convert_inline_html_to_markdown(m.group(1))}\n",
        content,
        flags=re.IGNORECASE,
    )

    content = _convert_inline_html_to_markdown(content)
    content = re.sub(r"\n{3,}", "\n\n", content).strip()
    return content


HTML_IMAGE_PATTERN = re.compile(r"(<img[^>]*?\bsrc=[\"'])([^\"']+)([\"'])", re.IGNORECASE)

STATIC_TEMP_MARKDOWN_ROOT = "/static/temp"
DEPRECATED_MEDIA_MARKDOWN_ROOT = "/media/articles"


def _starts_with_deprecated_media_root(path: str) -> bool:
    return (
        path == DEPRECATED_MEDIA_MARKDOWN_ROOT
        or path == DEPRECATED_MEDIA_MARKDOWN_ROOT.lstrip("/")
        or path.startswith(f"{DEPRECATED_MEDIA_MARKDOWN_ROOT}/")
        or path.startswith("media/articles/")
    )


def _convert_deprecated_media_root(path: str) -> str:
    if path == DEPRECATED_MEDIA_MARKDOWN_ROOT:
        return STATIC_TEMP_MARKDOWN_ROOT
    if path == DEPRECATED_MEDIA_MARKDOWN_ROOT.lstrip("/"):
        return STATIC_TEMP_MARKDOWN_ROOT
    if path.startswith(f"{DEPRECATED_MEDIA_MARKDOWN_ROOT}/"):
        return f"{STATIC_TEMP_MARKDOWN_ROOT}/{path[len(f'{DEPRECATED_MEDIA_MARKDOWN_ROOT}/'):]}"
    if path.startswith("media/articles/"):
        return f"{STATIC_TEMP_MARKDOWN_ROOT}/{path[len('media/articles/'):]}"
    return path


def normalize_source_markdown_path(source_path: str, *, reject_deprecated_media_root: bool = True) -> str:
    """Normalize incoming source_markdown_path to /static/temp root."""
    path = (source_path or "").strip().replace("\\", "/")
    if not path:
        return ""
    if _starts_with_deprecated_media_root(path):
        if reject_deprecated_media_root:
            raise ValueError("source_markdown_path 不再支持 /media/articles，请改用 /static/temp")
        path = _convert_deprecated_media_root(path)
    if path == STATIC_TEMP_MARKDOWN_ROOT:
        return path
    if path == STATIC_TEMP_MARKDOWN_ROOT.lstrip("/"):
        return STATIC_TEMP_MARKDOWN_ROOT
    if path.startswith("/static/temp/"):
        return path
    if path.startswith("static/temp/"):
        return f"/{path}"
    if path.startswith("/temp/"):
        return f"/static{path}"
    if path.startswith("temp/"):
        return f"/static/{path}"
    if path.startswith("/"):
        return f"{STATIC_TEMP_MARKDOWN_ROOT}{path}"
    return f"{STATIC_TEMP_MARKDOWN_ROOT}/{path}"


def _split_markdown_source_root(
    normalized_source_path: str, *, reject_deprecated_media_root: bool = True
) -> tuple[str, str]:
    normalized = normalize_source_markdown_path(
        normalized_source_path,
        reject_deprecated_media_root=reject_deprecated_media_root,
    )
    if normalized == STATIC_TEMP_MARKDOWN_ROOT:
        return STATIC_TEMP_MARKDOWN_ROOT, ""
    if normalized.startswith(f"{STATIC_TEMP_MARKDOWN_ROOT}/"):
        return STATIC_TEMP_MARKDOWN_ROOT, normalized[len(f"{STATIC_TEMP_MARKDOWN_ROOT}/") :]
    raise ValueError("source_markdown_path 必须位于 /static/temp 下")


def resolve_article_markdown_dir(source_path: str) -> tuple[Path, str]:
    """
    Return (absolute image dir path, normalized_source_markdown_path).
    Image dir is .../<article_dir>/img under static/temp.
    """
    normalized = normalize_source_markdown_path(source_path)
    root_prefix, md_rel = _split_markdown_source_root(normalized)
    if not md_rel:
        raise ValueError("source_markdown_path 不能为空")
    article_dir_rel = posixpath.dirname(md_rel)
    image_dir = Path(settings.BASE_DIR) / "static" / "temp" / article_dir_rel / "img"
    return image_dir, normalized


def _split_fenced_and_plain(markdown_content: str) -> list[tuple[bool, str]]:
    """Split markdown into (is_code_block, text) chunks."""
    chunks: list[tuple[bool, str]] = []
    cursor = 0
    for match in FENCED_CODE_BLOCK_PATTERN.finditer(markdown_content or ""):
        start, end = match.span()
        if start > cursor:
            chunks.append((False, markdown_content[cursor:start]))
        chunks.append((True, markdown_content[start:end]))
        cursor = end
    if cursor < len(markdown_content or ""):
        chunks.append((False, (markdown_content or "")[cursor:]))
    return chunks


def _normalize_ref_value(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    if value.startswith("<") and ">" in value:
        return value[1 : value.index(">")].strip()
    if " " in value:
        return value.split(" ", 1)[0].strip()
    return value


def _find_closing_paren(text: str, start: int) -> int:
    depth = 1
    idx = start
    in_single = False
    in_double = False
    while idx < len(text):
        ch = text[idx]
        if ch == "\\":
            idx += 2
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif not in_single and not in_double:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return idx
        idx += 1
    return -1


def _iter_markdown_image_destinations(text: str) -> list[tuple[int, int, str]]:
    """
    Return list of (start_idx, end_idx, raw_destination_inside_parentheses)
    for markdown image syntaxes ![alt](destination).
    """
    refs: list[tuple[int, int, str]] = []
    cursor = 0
    while cursor < len(text):
        marker = text.find("![", cursor)
        if marker < 0:
            break
        link_open = text.find("](", marker + 2)
        if link_open < 0:
            break
        dest_start = link_open + 2
        dest_end = _find_closing_paren(text, dest_start)
        if dest_end < 0:
            cursor = link_open + 2
            continue
        refs.append((dest_start, dest_end, text[dest_start:dest_end]))
        cursor = dest_end + 1
    return refs


def _replace_destination_path(raw_destination: str, old_path: str, new_path: str) -> str:
    leading_ws_len = len(raw_destination) - len(raw_destination.lstrip())
    leading = raw_destination[:leading_ws_len]
    body = raw_destination[leading_ws_len:]

    if body.startswith("<") and ">" in body:
        right = body.index(">")
        tail = body[right + 1 :]
        return f"{leading}<{new_path}>{tail}"

    if not body:
        return raw_destination

    parts = body.split(None, 1)
    token = parts[0]
    tail = body[len(token) :]
    if token == old_path:
        return f"{leading}{new_path}{tail}"

    return raw_destination.replace(old_path, new_path, 1)


def _is_remote_or_abs_path(path: str) -> bool:
    p = (path or "").lower()
    return (
        p.startswith("http://")
        or p.startswith("https://")
        or p.startswith("data:")
        or p.startswith("blob:")
        or p.startswith("#")
    )


def _resolve_local_ref_to_static_url(local_ref: str, source_markdown_path: str) -> str:
    src = (local_ref or "").strip().replace("\\", "/")
    if not src:
        return src
    if src.startswith("/static/") or src.startswith("/media/"):
        return src
    if src.startswith("static/"):
        return f"/{src}"
    if src.startswith("media/"):
        return f"/{src}"
    if src.startswith("temp/"):
        return f"/static/{src}"

    try:
        root_prefix, source_rel = _split_markdown_source_root(
            source_markdown_path,
            reject_deprecated_media_root=False,
        )
    except ValueError:
        root_prefix, source_rel = STATIC_TEMP_MARKDOWN_ROOT, ""
    if src.startswith("/"):
        return f"{root_prefix}{src}"
    source_dir = posixpath.dirname(source_rel)
    resolved = posixpath.normpath(posixpath.join(source_dir, src))
    return f"{root_prefix}/{resolved.lstrip('/')}"


def rewrite_markdown_local_refs_for_response(markdown_content: str, source_markdown_path: str) -> str:
    """
    Rewrite local image refs in markdown to /static/... urls for API response.
    Code blocks remain unchanged.
    """
    chunks = _split_fenced_and_plain(markdown_content or "")
    rebuilt: list[str] = []

    for is_code, chunk in chunks:
        if is_code:
            rebuilt.append(chunk)
            continue

        md_spans: list[tuple[int, int, str]] = []
        for start, end, raw_destination in _iter_markdown_image_destinations(chunk):
            src = _normalize_ref_value(raw_destination)
            if not src or _is_remote_or_abs_path(src):
                continue
            rewritten = _resolve_local_ref_to_static_url(src, source_markdown_path)
            if rewritten == src:
                continue
            new_destination = _replace_destination_path(raw_destination, src, rewritten)
            md_spans.append((start, end, new_destination))

        if md_spans:
            merged: list[str] = []
            cursor = 0
            for start, end, replacement in md_spans:
                merged.append(chunk[cursor:start])
                merged.append(replacement)
                cursor = end
            merged.append(chunk[cursor:])
            chunk = "".join(merged)

        def html_repl(match: re.Match[str]) -> str:
            prefix, raw_src, suffix = match.groups()
            src = (raw_src or "").strip()
            if not src or _is_remote_or_abs_path(src):
                return match.group(0)
            rewritten = _resolve_local_ref_to_static_url(src, source_markdown_path)
            if rewritten == src:
                return match.group(0)
            return f"{prefix}{rewritten}{suffix}"

        updated = HTML_IMAGE_PATTERN.sub(html_repl, chunk)
        rebuilt.append(updated)

    return "".join(rebuilt)


def replace_refs_outside_codeblocks(markdown_content: str, replacements: dict[str, str]) -> str:
    """Literal ref replacement for non-code markdown segments."""
    if not replacements:
        return markdown_content or ""
    chunks = _split_fenced_and_plain(markdown_content or "")
    rebuilt: list[str] = []
    for is_code, chunk in chunks:
        if is_code:
            rebuilt.append(chunk)
            continue
        updated = chunk
        for old_ref, new_ref in replacements.items():
            if not old_ref or old_ref == new_ref:
                continue
            updated = updated.replace(old_ref, new_ref)
        rebuilt.append(updated)
    return "".join(rebuilt)


def save_local_images_and_rewrite_markdown(
    *,
    markdown_content: str,
    source_markdown_path: str,
    mappings: Iterable[dict],
    files,
) -> dict:
    """
    Save selected local images to <article_dir>/img and rewrite refs to img/<filename>.
    Supports /static/temp only.
    mappings item example: {"ref": "./img/a.png", "file_field": "file_0"}
    """
    image_dir, normalized_source_path = resolve_article_markdown_dir(source_markdown_path)
    image_dir.mkdir(parents=True, exist_ok=True)

    replacements: dict[str, str] = {}
    uploaded: list[dict] = []
    unresolved_refs: list[str] = []

    for item in mappings:
        ref = str(item.get("ref") or "").strip()
        file_field = str(item.get("file_field") or "").strip()
        if not ref:
            continue
        if not file_field:
            unresolved_refs.append(ref)
            continue
        uploaded_file = files.get(file_field)
        if uploaded_file is None:
            unresolved_refs.append(ref)
            continue

        filename = Path(uploaded_file.name).name
        if not filename:
            unresolved_refs.append(ref)
            continue

        dest = image_dir / filename
        with dest.open("wb") as output:
            for chunk in uploaded_file.chunks():
                output.write(chunk)

        new_ref = f"img/{filename}"
        replacements[ref] = new_ref
        uploaded.append(
            {
                "ref": ref,
                "saved_to": str(dest),
                "saved_url": f"{normalized_source_path.rsplit('/', 1)[0]}/img/{filename}",
            }
        )

    updated_markdown = replace_refs_outside_codeblocks(markdown_content or "", replacements)
    return {
        "markdown_content": updated_markdown,
        "source_markdown_path": normalized_source_path,
        "uploaded": uploaded,
        "unresolved_refs": sorted(set(unresolved_refs)),
    }
