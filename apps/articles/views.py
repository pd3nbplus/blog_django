from __future__ import annotations

import math
import os
import posixpath
import random
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.views import APIView

from apps.common.responses import error_response, success_response
from apps.common.serializers import EmptySerializer
from apps.users.models import UserSiteSettings

from .models import Article, Category, Collection, Comment
from .serializers import (
    AdminCategoryWriteSerializer,
    AdminCommentSerializer,
    ArticleDetailSerializer,
    ArticleListSerializer,
    ArticleWriteSerializer,
    CategorySerializer,
    CategoryTreeSerializer,
    CollectionDetailSerializer,
    CollectionListSerializer,
    CollectionWriteSerializer,
)
from .services import (
    html_to_markdown,
    normalize_source_markdown_path,
)

HOME_SUMMARY_CACHE_KEY = "home:summary:v4"
CATEGORY_TREE_CACHE_KEY = "categories:tree:v1"
PUBLIC_CACHE_TIMEOUT_SECONDS = 300
IMAGE_PROXY_HOST_SUFFIXES = ("csdnimg.cn",)
IMAGE_PROXY_TIMEOUT_SECONDS = 12
IMAGE_PROXY_MAX_BYTES = 10 * 1024 * 1024
MEDIA_UPLOAD_MAX_BYTES = 5 * 1024 * 1024


def invalidate_public_cache() -> None:
    cache.delete_many([HOME_SUMMARY_CACHE_KEY, CATEGORY_TREE_CACHE_KEY])


def _with_collection_stats(queryset):
    return queryset.annotate(
        article_count=Count("articles", distinct=True),
        total_views=Coalesce(Sum("articles__view_count"), 0),
    )


def _bool_from_value(value, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _sanitize_upload_file_name(file_name: str, default_stem: str = "file") -> str:
    original = Path(file_name or "").name
    stem = slugify(Path(original).stem) or default_stem
    suffix = Path(original).suffix.lower()
    return f"{stem}{suffix}"


def _ensure_unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    index = 1
    while True:
        candidate = parent / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def _decode_uploaded_text(file_obj) -> str:
    raw = file_obj.read()
    for encoding in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def _resolve_source_markdown_absolute_path(normalized_source_path: str) -> Path:
    normalized = normalize_source_markdown_path(normalized_source_path)
    def _safe_rel_path(raw_rel: str) -> str:
        rel = posixpath.normpath((raw_rel or "").replace("\\", "/").strip("/"))
        if rel in {"", "."} or rel == ".." or rel.startswith("../"):
            raise ValueError("source_markdown_path 非法")
        return rel

    if normalized.startswith("/static/temp/"):
        rel = _safe_rel_path(normalized[len("/static/temp/") :])
        return Path(settings.BASE_DIR) / "static" / "temp" / rel
    raise ValueError("source_markdown_path 必须位于 /static/temp 下")


def _sanitize_category_path_segment(name: str, *, fallback: str) -> str:
    value = (name or "").strip().replace("\\", "/")
    value = value.replace("/", "_")
    if not value or value in {".", ".."}:
        return fallback
    return value


def _sanitize_article_title_segment(title: str, *, fallback: str = "article") -> str:
    value = (title or "").strip().replace("\\", "/")
    value = value.replace("/", "_")
    if not value or value in {".", ".."}:
        return fallback
    return value


def _category_lineage_segments(category: Category | None) -> list[str]:
    if category is None:
        return ["uncategorized"]
    lineage: list[str] = []
    cursor: Category | None = category
    while cursor is not None:
        lineage.append(
            _sanitize_category_path_segment(
                cursor.name,
                fallback=f"category_{cursor.id}",
            )
        )
        cursor = cursor.parent
    lineage.reverse()
    return lineage or ["uncategorized"]


def _build_article_archive_markdown_path(*, title: str, category: Category | None) -> tuple[Path, str]:
    title_segment = _sanitize_article_title_segment(title, fallback="article")
    rel = Path("temp") / Path(*_category_lineage_segments(category)) / f"{title_segment}.md"
    destination = Path(settings.BASE_DIR) / "static" / rel
    source_markdown_path = f"/static/{rel.as_posix()}"
    return destination, source_markdown_path


def _build_article_archive_image_path(*, title: str, category: Category | None, suffix: str) -> tuple[Path, str]:
    title_segment = _sanitize_article_title_segment(title, fallback="article")
    ext = (suffix or "").lower()
    if not ext.startswith("."):
        ext = f".{ext}" if ext else ""
    if not ext:
        ext = ".png"
    rel = Path("temp") / Path(*_category_lineage_segments(category)) / "img" / f"{title_segment}{ext}"
    destination = Path(settings.BASE_DIR) / "static" / rel
    cover_path = f"/static/{rel.as_posix()}"
    return destination, cover_path


def _persist_article_markdown_archive(article: Article) -> None:
    destination, source_markdown_path = _build_article_archive_markdown_path(
        title=article.title,
        category=article.category,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(article.markdown_content or "", encoding="utf-8")
    if article.source_markdown_path != source_markdown_path:
        article.source_markdown_path = source_markdown_path
        article.save(update_fields=["source_markdown_path", "updated_at"])


def _category_icon_path(uploaded_file, *, category: Category) -> str:
    lineage: list[str] = []
    cursor: Category | None = category
    while cursor is not None:
        lineage.append(
            _sanitize_category_path_segment(
                cursor.name,
                fallback=f"category_{cursor.id}",
            )
        )
        cursor = cursor.parent
    lineage.reverse()

    suffix = Path(uploaded_file.name or "").suffix.lower() or ".png"
    icon_name = f"{lineage[-1]}{suffix}"
    icon_dir = Path(settings.BASE_DIR) / "static" / "temp" / Path(*lineage) / "img"
    icon_dir.mkdir(parents=True, exist_ok=True)
    destination = icon_dir / icon_name
    with destination.open("wb") as output:
        for chunk in uploaded_file.chunks():
            output.write(chunk)
    return destination.relative_to(Path(settings.BASE_DIR) / "static").as_posix()


def _get_media_root() -> Path:
    return (Path(settings.BASE_DIR) / "static").resolve()


def _resolve_media_path(relative_path: str) -> tuple[Path, str]:
    root = _get_media_root()
    normalized = (relative_path or "").replace("\\", "/").strip("/")
    if not normalized:
        return root, ""

    normalized = posixpath.normpath(normalized)
    if normalized in {".", ""}:
        return root, ""
    if normalized == ".." or normalized.startswith("../"):
        raise ValueError("path 不允许越界")

    abs_path = (root / normalized).resolve()
    if not abs_path.is_relative_to(root):
        raise ValueError("path 不允许越界")
    return abs_path, normalized


def _build_media_file_url(rel_file_path: str) -> str:
    encoded = quote(rel_file_path.replace("\\", "/"), safe="/.-_~")
    return f"/static/{encoded}"


def _list_media_directories() -> list[str]:
    root = _get_media_root()
    if not root.exists():
        return []

    directories: list[str] = []
    for dir_path, dir_names, _ in os.walk(root):
        dir_names.sort()
        current = Path(dir_path)
        if current == root:
            continue
        directories.append(current.relative_to(root).as_posix())
    directories.sort()
    return directories


def _is_allowed_image_proxy_host(hostname: str) -> bool:
    host = (hostname or "").strip(".").lower()
    if not host:
        return False
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in IMAGE_PROXY_HOST_SUFFIXES)


class PublicImageProxyAPIView(APIView):
    serializer_class = EmptySerializer
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        raw_url = str(request.query_params.get("url") or "").strip()
        if not raw_url:
            return HttpResponse("missing url", status=status.HTTP_400_BAD_REQUEST, content_type="text/plain; charset=utf-8")

        parsed = urlparse(raw_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return HttpResponse("invalid url", status=status.HTTP_400_BAD_REQUEST, content_type="text/plain; charset=utf-8")
        if not _is_allowed_image_proxy_host(parsed.hostname or ""):
            return HttpResponse("host not allowed", status=status.HTTP_400_BAD_REQUEST, content_type="text/plain; charset=utf-8")

        upstream_url = parsed._replace(fragment="").geturl()
        upstream_request = Request(
            upstream_url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; PdnbplusBlog/1.0)",
                "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            },
        )

        try:
            with urlopen(upstream_request, timeout=IMAGE_PROXY_TIMEOUT_SECONDS) as upstream:
                content_type = getattr(upstream.headers, "get_content_type", lambda: upstream.headers.get("Content-Type", ""))()
                content_length = upstream.headers.get("Content-Length")
                if content_length:
                    try:
                        if int(content_length) > IMAGE_PROXY_MAX_BYTES:
                            return HttpResponse(
                                "image too large",
                                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                                content_type="text/plain; charset=utf-8",
                            )
                    except ValueError:
                        pass

                content = upstream.read(IMAGE_PROXY_MAX_BYTES + 1)
        except HTTPError:
            return HttpResponse("upstream rejected", status=status.HTTP_502_BAD_GATEWAY, content_type="text/plain; charset=utf-8")
        except URLError:
            return HttpResponse("upstream unavailable", status=status.HTTP_502_BAD_GATEWAY, content_type="text/plain; charset=utf-8")
        except TimeoutError:
            return HttpResponse("upstream timeout", status=status.HTTP_504_GATEWAY_TIMEOUT, content_type="text/plain; charset=utf-8")

        if len(content) > IMAGE_PROXY_MAX_BYTES:
            return HttpResponse("image too large", status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, content_type="text/plain; charset=utf-8")

        normalized_type = (content_type or "").split(";", 1)[0].strip().lower()
        if not normalized_type.startswith("image/"):
            return HttpResponse("upstream is not image", status=status.HTTP_502_BAD_GATEWAY, content_type="text/plain; charset=utf-8")

        response = HttpResponse(content, content_type=normalized_type)
        response["Cache-Control"] = "public, max-age=86400"
        return response


class HomeSummaryAPIView(APIView):
    serializer_class = EmptySerializer
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        cached = cache.get(HOME_SUMMARY_CACHE_KEY)
        if cached is not None:
            return success_response(data=cached)

        latest_articles_queryset = Article.objects.select_related("author", "category").filter(status=Article.Status.PUBLISHED)
        paper_root_category = Category.objects.filter(name="论文阅读").order_by("id").first()
        if paper_root_category is None:
            latest_articles = latest_articles_queryset.none()
        else:
            paper_category_ids = [paper_root_category.id]
            pending_parent_ids = [paper_root_category.id]
            while pending_parent_ids:
                child_ids = list(Category.objects.filter(parent_id__in=pending_parent_ids).values_list("id", flat=True))
                if not child_ids:
                    break
                paper_category_ids.extend(child_ids)
                pending_parent_ids = child_ids

            latest_articles = latest_articles_queryset.filter(category_id__in=paper_category_ids).order_by("-published_at", "-created_at")[:15]
        popular_articles = (
            Article.objects.select_related("author", "category")
            .filter(status=Article.Status.PUBLISHED)
            .order_by("-view_count", "-published_at")[:10]
        )
        pinned_collections = _with_collection_stats(Collection.objects.filter(is_pinned=True)).order_by("order", "-updated_at", "-id")[:3]
        categories = Category.objects.filter(parent__isnull=True).order_by("order", "id")
        default_owner = get_user_model().objects.filter(is_superuser=True).order_by("id").first()
        if default_owner is None:
            default_owner = get_user_model().objects.filter(is_staff=True).order_by("id").first()

        site_profile = {
            "display_name": default_owner.username if default_owner else "",
            "home_avatar_path": "",
            "home_hero_path": "",
        }
        if default_owner:
            site_settings = UserSiteSettings.objects.filter(user=default_owner).first()
            if site_settings:
                site_profile["home_avatar_path"] = site_settings.home_avatar_path or ""
                site_profile["home_hero_path"] = site_settings.home_hero_path or ""

        payload = {
            "stats": {
                "article_count": Article.objects.filter(status=Article.Status.PUBLISHED).count(),
                "category_count": Category.objects.count(),
                "collection_count": Collection.objects.count(),
            },
            "site_profile": site_profile,
            "latest_articles": ArticleListSerializer(latest_articles, many=True).data,
            "popular_articles": ArticleListSerializer(popular_articles, many=True).data,
            "pinned_collections": CollectionListSerializer(pinned_collections, many=True).data,
            "categories": CategoryTreeSerializer(categories, many=True).data,
        }
        cache.set(HOME_SUMMARY_CACHE_KEY, payload, PUBLIC_CACHE_TIMEOUT_SECONDS)
        return success_response(data=payload)


class HomeRecommendationsAPIView(APIView):
    serializer_class = EmptySerializer
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        page_raw = request.query_params.get("page", 1)
        page_size_raw = request.query_params.get("page_size", 8)
        seed_raw = request.query_params.get("seed")
        category_raw = request.query_params.get("category")

        try:
            page = max(int(page_raw), 1)
        except (TypeError, ValueError):
            page = 1

        try:
            page_size = int(page_size_raw)
        except (TypeError, ValueError):
            page_size = 8
        page_size = min(max(page_size, 1), 50)

        if seed_raw is None:
            seed = random.SystemRandom().randint(1, 2_147_483_647)
        else:
            try:
                seed = int(seed_raw)
            except (TypeError, ValueError):
                seed = random.SystemRandom().randint(1, 2_147_483_647)

        recommendations_queryset = Article.objects.select_related("author", "category").filter(status=Article.Status.PUBLISHED)
        if category_raw is not None:
            try:
                category_id = int(category_raw)
            except (TypeError, ValueError):
                recommendations_queryset = recommendations_queryset.none()
            else:
                category = Category.objects.filter(id=category_id).first()
                if category is None:
                    recommendations_queryset = recommendations_queryset.none()
                elif category.level == 1:
                    category_ids = [category.id]
                    pending_parent_ids = [category.id]
                    while pending_parent_ids:
                        child_ids = list(Category.objects.filter(parent_id__in=pending_parent_ids).values_list("id", flat=True))
                        if not child_ids:
                            break
                        category_ids.extend(child_ids)
                        pending_parent_ids = child_ids
                    recommendations_queryset = recommendations_queryset.filter(category_id__in=category_ids)
                else:
                    recommendations_queryset = recommendations_queryset.filter(category_id=category.id)

        articles = list(
            recommendations_queryset.only(
                "id",
                "title",
                "slug",
                "summary",
                "cover_path",
                "status",
                "view_count",
                "markdown_content",
                "published_at",
                "created_at",
                "updated_at",
                "author__id",
                "author__username",
                "category__id",
                "category__name",
                "category__slug",
                "category__level",
                "category__parent_id",
                "category__icon_path",
                "category__order",
            )
        )

        total = len(articles)
        if total == 0:
            payload = {
                "count": 0,
                "page": page,
                "page_size": page_size,
                "num_pages": 0,
                "has_more": False,
                "seed": seed,
                "results": [],
            }
            return success_response(data=payload)

        now = timezone.now()
        max_view_count = max((article.view_count for article in articles), default=0)
        view_denom = math.log1p(max_view_count + 1)
        rng = random.Random(seed)

        weighted_pairs: list[tuple[float, Article]] = []
        for article in articles:
            publish_time = article.published_at or article.created_at or now
            age_days = max((now - publish_time).total_seconds() / 86400, 0.0)

            view_score = (math.log1p(article.view_count + 1) / view_denom) if view_denom > 0 else 0.0
            recency_score = math.exp(-age_days / 90.0)
            weight = 0.7 * view_score + 0.3 * recency_score + 1e-6

            rand_value = max(rng.random(), 1e-12)
            random_key = -math.log(rand_value) / weight
            weighted_pairs.append((random_key, article))

        weighted_pairs.sort(key=lambda item: item[0])
        ordered_articles = [item[1] for item in weighted_pairs]

        start = (page - 1) * page_size
        end = start + page_size
        page_articles = ordered_articles[start:end]
        num_pages = (total + page_size - 1) // page_size

        payload = {
            "count": total,
            "page": page,
            "page_size": page_size,
            "num_pages": num_pages,
            "has_more": end < total,
            "seed": seed,
            "results": ArticleListSerializer(page_articles, many=True).data,
        }
        return success_response(data=payload)


class AdminDashboardSummaryAPIView(APIView):
    serializer_class = EmptySerializer
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        user_model = get_user_model()
        user_count = user_model.objects.count()
        article_count = Article.objects.count()
        category_count = Category.objects.count()
        collection_count = Collection.objects.count()
        total_views = (Article.objects.aggregate(total=Sum("view_count")).get("total") or 0) / 10000

        category_articles: dict[str, int] = {}
        top_level_categories = Category.objects.filter(parent__isnull=True).order_by("order", "id")
        for category in top_level_categories:
            direct_count = Article.objects.filter(category=category).count()
            sub_count = Article.objects.filter(category__parent=category).count()
            category_articles[category.name] = direct_count + sub_count

        payload = {
            "user_count": user_count,
            "article_count": article_count,
            "category_count": category_count,
            "collection_count": collection_count,
            "total_views": round(total_views, 2),
            "category_articles": category_articles,
        }
        return success_response(data=payload)


class PublicArticleViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [permissions.AllowAny]
    lookup_field = "id"

    def get_queryset(self):
        queryset = Article.objects.select_related("author", "category").filter(status=Article.Status.PUBLISHED)
        q = self.request.query_params.get("q", "").strip()
        category_id = self.request.query_params.get("category")
        collection_id = self.request.query_params.get("collection")
        if q:
            queryset = queryset.filter(Q(title__icontains=q) | Q(summary__icontains=q))
        if category_id:
            try:
                category = Category.objects.get(id=category_id)
            except (Category.DoesNotExist, ValueError, TypeError):
                queryset = queryset.none()
            else:
                if category.level == 1:
                    child_ids = list(Category.objects.filter(parent_id=category.id).values_list("id", flat=True))
                    queryset = queryset.filter(category_id__in=child_ids)
                else:
                    queryset = queryset.filter(category_id=category.id)
        if collection_id:
            try:
                queryset = queryset.filter(collections__id=int(collection_id))
            except (ValueError, TypeError):
                queryset = queryset.none()
        return queryset.order_by("-is_pinned", "-published_at", "-created_at").distinct()

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ArticleDetailSerializer
        return ArticleListSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["resolve_markdown_links"] = True
        return context

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        Article.objects.filter(pk=instance.pk).update(view_count=F("view_count") + 1)
        instance.refresh_from_db()
        serializer = self.get_serializer(instance)
        return success_response(data=serializer.data)


class CategoryViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Category.objects.select_related("parent").all().order_by("order", "id")
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = "id"

    def list(self, request, *args, **kwargs):
        root_only = request.query_params.get("root_only") == "1"
        queryset = self.get_queryset()
        if root_only:
            queryset = queryset.filter(parent__isnull=True)
        serializer = self.get_serializer(queryset, many=True)
        return success_response(data=serializer.data)

    def retrieve(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object())
        return success_response(data=serializer.data)

    @action(detail=False, methods=["get"], url_path="tree")
    def tree(self, request):
        cached = cache.get(CATEGORY_TREE_CACHE_KEY)
        if cached is not None:
            return success_response(data=cached)
        roots = Category.objects.filter(parent__isnull=True).order_by("order", "id")
        data = CategoryTreeSerializer(roots, many=True).data
        cache.set(CATEGORY_TREE_CACHE_KEY, data, PUBLIC_CACHE_TIMEOUT_SECONDS)
        return success_response(data=data)


class PublicCollectionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [permissions.AllowAny]
    serializer_class = CollectionListSerializer
    lookup_field = "id"

    def get_queryset(self):
        queryset = _with_collection_stats(Collection.objects.prefetch_related("articles")).order_by("-is_pinned", "order", "-updated_at", "-id")
        q = self.request.query_params.get("q", "").strip()
        if q:
            queryset = queryset.filter(Q(name__icontains=q) | Q(summary__icontains=q) | Q(slug__icontains=q))
        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return success_response(data=serializer.data)

    def retrieve(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object())
        return success_response(data=serializer.data)


class AdminArticleViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAdminUser]
    queryset = Article.objects.select_related("author", "category").all().order_by("-updated_at")
    ORDERING_FIELDS = {"updated_at", "created_at", "published_at", "view_count", "title", "status"}

    @staticmethod
    def _collect_category_ids(category: Category) -> list[int]:
        if category.level != 1:
            return [category.id]
        category_ids = [category.id]
        pending_parent_ids = [category.id]
        while pending_parent_ids:
            child_ids = list(Category.objects.filter(parent_id__in=pending_parent_ids).values_list("id", flat=True))
            if not child_ids:
                break
            category_ids.extend(child_ids)
            pending_parent_ids = child_ids
        return category_ids

    def get_queryset(self):
        queryset = super().get_queryset()
        q = self.request.query_params.get("q", "").strip()
        status_filter = self.request.query_params.get("status", "").strip()
        category_filter = self.request.query_params.get("category")
        ordering = self.request.query_params.get("ordering", "").strip()

        if q:
            queryset = queryset.filter(Q(title__icontains=q) | Q(summary__icontains=q) | Q(slug__icontains=q))
        if status_filter in {Article.Status.DRAFT, Article.Status.PUBLISHED, Article.Status.ARCHIVED}:
            queryset = queryset.filter(status=status_filter)
        if category_filter:
            try:
                category = Category.objects.get(id=int(category_filter))
            except (Category.DoesNotExist, ValueError, TypeError):
                queryset = queryset.none()
            else:
                queryset = queryset.filter(category_id__in=self._collect_category_ids(category))

        if ordering:
            ordering_field = ordering[1:] if ordering.startswith("-") else ordering
            if ordering_field in self.ORDERING_FIELDS:
                return queryset.order_by(ordering, "-id")
        return queryset.order_by("-updated_at", "-id")

    def get_serializer_class(self):
        if self.action in ["list", "retrieve"]:
            return ArticleDetailSerializer if self.action == "retrieve" else ArticleListSerializer
        return ArticleWriteSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["resolve_markdown_links"] = False
        return context

    def retrieve(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object())
        return success_response(data=serializer.data)

    def create(self, request, *args, **kwargs):
        payload = request.data.copy()
        payload.setdefault("author", request.user.id)
        serializer = self.get_serializer(data=payload)
        serializer.is_valid(raise_exception=True)
        article = serializer.save()
        _persist_article_markdown_archive(article)
        invalidate_public_cache()
        return success_response(data=self.get_serializer(article).data, message="created")

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        article = serializer.save()
        _persist_article_markdown_archive(article)
        invalidate_public_cache()
        return success_response(data=self.get_serializer(article).data, message="updated")

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        invalidate_public_cache()
        return success_response(message="deleted")

    @action(
        detail=False,
        methods=["post"],
        url_path="resolve-local-images",
        parser_classes=[MultiPartParser, FormParser],
    )
    def resolve_local_images(self, request):
        markdown_content = request.data.get("markdown_content", "")
        source_markdown_path = request.data.get("source_markdown_path", "")
        normalized_source = ""
        if source_markdown_path:
            try:
                normalized_source = normalize_source_markdown_path(source_markdown_path)
            except ValueError as exc:
                return error_response(message=str(exc), code=400)

        # Keep markdown refs as-is. Do not persist referenced images physically.
        return success_response(
            data={
                "markdown_content": markdown_content,
                "source_markdown_path": normalized_source,
                "uploaded": [],
                "unresolved_refs": [],
            }
        )

    @action(
        detail=False,
        methods=["post"],
        url_path="upload-markdown",
        parser_classes=[MultiPartParser, FormParser],
    )
    def upload_markdown(self, request):
        markdown_file = request.FILES.get("markdown_file") or request.FILES.get("markdown-file")
        if markdown_file is None:
            return error_response(message="请上传 markdown_file 文件", code=400)

        suffix = Path(markdown_file.name).suffix.lower()
        if suffix not in {".md", ".markdown", ".txt", ".html", ".htm"}:
            return error_response(message="仅支持 md/markdown/txt/html 文件", code=400)

        text_content = _decode_uploaded_text(markdown_file)
        markdown_content = html_to_markdown(text_content) if suffix in {".html", ".htm"} else text_content

        if str(request.data.get("source_markdown_path") or "").strip():
            return error_response(message="禁止传 source_markdown_path，路径由后端自动归档", code=400)
        title = str(request.data.get("title") or "").strip()
        if not title:
            return error_response(message="请传 title（文章标题）", code=400)
        category_id_raw = request.data.get("category")
        category: Category | None = None
        if category_id_raw not in {None, ""}:
            try:
                category = Category.objects.get(id=int(category_id_raw))
            except (Category.DoesNotExist, ValueError, TypeError):
                return error_response(message="category 无效", code=400)

        destination, normalized_source = _build_article_archive_markdown_path(title=title, category=category)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(markdown_content, encoding="utf-8")
        return success_response(
            data={
                "markdown_content": markdown_content,
                "source_markdown_path": normalized_source,
                "saved_to": str(destination),
            }
        )

    @action(
        detail=False,
        methods=["post"],
        url_path="upload-cover",
        parser_classes=[MultiPartParser, FormParser],
    )
    def upload_cover(self, request):
        cover_file = request.FILES.get("cover_file") or request.FILES.get("file")
        if cover_file is None:
            return error_response(message="请上传 cover_file 文件", code=400)

        if str(request.data.get("source_markdown_path") or "").strip():
            return error_response(message="禁止传 source_markdown_path，路径由后端自动归档", code=400)
        title = str(request.data.get("title") or "").strip()
        if not title:
            return error_response(message="请传 title（文章标题）", code=400)
        category_id_raw = request.data.get("category")
        category: Category | None = None
        if category_id_raw not in {None, ""}:
            try:
                category = Category.objects.get(id=int(category_id_raw))
            except (Category.DoesNotExist, ValueError, TypeError):
                return error_response(message="category 无效", code=400)

        destination, cover_path = _build_article_archive_image_path(
            title=title,
            category=category,
            suffix=Path(cover_file.name).suffix.lower(),
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("wb") as output:
            for chunk in cover_file.chunks():
                output.write(chunk)

        return success_response(
            data={
                "cover_path": cover_path,
                "saved_to": str(destination),
            }
        )


class AdminCollectionViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAdminUser]
    queryset = _with_collection_stats(Collection.objects.prefetch_related("articles")).all().order_by("-is_pinned", "order", "-updated_at", "-id")
    ORDERING_FIELDS = {"updated_at", "created_at", "name", "is_pinned", "order", "article_count", "total_views"}

    def get_queryset(self):
        queryset = super().get_queryset()
        q = self.request.query_params.get("q", "").strip()
        pinned_raw = self.request.query_params.get("is_pinned")
        ordering = self.request.query_params.get("ordering", "").strip()

        if q:
            queryset = queryset.filter(Q(name__icontains=q) | Q(summary__icontains=q) | Q(slug__icontains=q))

        if pinned_raw is not None and str(pinned_raw).strip() != "":
            queryset = queryset.filter(is_pinned=_bool_from_value(pinned_raw, default=False))

        if ordering:
            ordering_field = ordering[1:] if ordering.startswith("-") else ordering
            if ordering_field in self.ORDERING_FIELDS:
                return queryset.order_by(ordering, "-id")
        return queryset.order_by("-is_pinned", "order", "-updated_at", "-id")

    def get_serializer_class(self):
        if self.action in {"create", "update", "partial_update"}:
            return CollectionWriteSerializer
        if self.action == "retrieve":
            return CollectionDetailSerializer
        return CollectionListSerializer

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.get_queryset())
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return success_response(data=serializer.data)

    def retrieve(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object())
        return success_response(data=serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        collection = serializer.save()
        invalidate_public_cache()
        output = CollectionDetailSerializer(_with_collection_stats(Collection.objects.filter(pk=collection.pk)).first())
        return success_response(data=output.data, message="created")

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        collection = serializer.save()
        invalidate_public_cache()
        output = CollectionDetailSerializer(_with_collection_stats(Collection.objects.filter(pk=collection.pk)).first())
        return success_response(data=output.data, message="updated")

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        invalidate_public_cache()
        return success_response(message="deleted")


class AdminCategoryViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAdminUser]
    queryset = Category.objects.select_related("parent").all().order_by("order", "id")
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_serializer_class(self):
        if self.action in {"create", "update", "partial_update"}:
            return AdminCategoryWriteSerializer
        if self.action == "tree":
            return CategoryTreeSerializer
        return CategorySerializer

    def list(self, request, *args, **kwargs):
        serializer = CategorySerializer(self.get_queryset(), many=True)
        return success_response(data=serializer.data)

    def retrieve(self, request, *args, **kwargs):
        serializer = CategorySerializer(self.get_object())
        return success_response(data=serializer.data)

    @action(detail=False, methods=["get"], url_path="tree")
    def tree(self, request):
        roots = Category.objects.filter(parent__isnull=True).order_by("order", "id")
        serializer = CategoryTreeSerializer(roots, many=True)
        return success_response(data=serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        parent = validated.get("parent")
        icon_file = validated.get("icon_file")
        instance = Category.objects.create(
            name=validated["name"],
            slug=validated.get("slug") or "",
            parent=parent,
            order=validated.get("order", 0),
            level=1 if parent is None else parent.level + 1,
        )

        if icon_file is not None:
            instance.icon_path = _category_icon_path(icon_file, category=instance)
            instance.save(update_fields=["icon_path", "updated_at"])

        invalidate_public_cache()
        return success_response(data=CategorySerializer(instance).data, message="created")

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        new_parent = validated.get("parent", instance.parent)
        if new_parent and new_parent.id == instance.id:
            return error_response(message="父分类不能是自己", code=400)

        cursor = new_parent
        while cursor is not None:
            if cursor.id == instance.id:
                return error_response(message="父分类不能是当前分类的子孙节点", code=400)
            cursor = cursor.parent

        if "name" in validated:
            instance.name = validated["name"]
        if "slug" in validated and validated["slug"]:
            instance.slug = validated["slug"]
        if "order" in validated:
            instance.order = validated["order"]
        instance.parent = new_parent
        instance.level = 1 if new_parent is None else new_parent.level + 1

        icon_file = validated.get("icon_file")
        if icon_file is not None:
            instance.icon_path = _category_icon_path(icon_file, category=instance)

        instance.save()
        invalidate_public_cache()
        return success_response(data=CategorySerializer(instance).data, message="updated")

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        invalidate_public_cache()
        return success_response(message="deleted")


class AdminCommentViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAdminUser]
    queryset = Comment.objects.select_related("article").all().order_by("-created_at")
    serializer_class = AdminCommentSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        q = self.request.query_params.get("q", "").strip()
        approved = self.request.query_params.get("approved")
        if q:
            queryset = queryset.filter(
                Q(content__icontains=q)
                | Q(author_name__icontains=q)
                | Q(author_email__icontains=q)
                | Q(article__title__icontains=q)
            )
        if approved is not None:
            queryset = queryset.filter(is_approved=_bool_from_value(approved))
        return queryset

    def retrieve(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object())
        return success_response(data=serializer.data)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return success_response(data=serializer.data, message="updated")

    @action(detail=True, methods=["patch"], url_path="approve")
    def approve(self, request, pk=None):
        instance = self.get_object()
        instance.is_approved = _bool_from_value(request.data.get("approved"), default=True)
        instance.save(update_fields=["is_approved", "updated_at"])
        serializer = self.get_serializer(instance)
        return success_response(data=serializer.data, message="updated")

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return success_response(message="deleted")


class AdminMediaListAPIView(APIView):
    serializer_class = EmptySerializer
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        requested_path = request.query_params.get("path", "")
        include_files = _bool_from_value(request.query_params.get("include_files"), default=True)
        try:
            directory, normalized = _resolve_media_path(requested_path)
        except ValueError as exc:
            return error_response(message=str(exc), code=400, status_code=status.HTTP_400_BAD_REQUEST)

        if not directory.exists():
            return success_response(data={"current_path": normalized, "directories": [], "files": []})
        if not directory.is_dir():
            return error_response(message="path 不是目录", code=400, status_code=status.HTTP_400_BAD_REQUEST)

        directories: list[str] = []
        files: list[dict] = []
        for item in sorted(directory.iterdir(), key=lambda p: p.name):
            if item.is_dir():
                directories.append(item.name)
                continue
            if not include_files:
                continue
            rel_path = f"{normalized}/{item.name}" if normalized else item.name
            files.append(
                {
                    "name": item.name,
                    "url": _build_media_file_url(rel_path),
                    "size": item.stat().st_size,
                    "updated_at": timezone.datetime.fromtimestamp(
                        item.stat().st_mtime, tz=timezone.get_current_timezone()
                    ).isoformat(),
                    "is_image": item.suffix.lower() in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp"},
                }
            )

        return success_response(
            data={
                "current_path": normalized,
                "directories": directories,
                "files": files,
            }
        )


class AdminMediaDirectoryTreeAPIView(APIView):
    serializer_class = EmptySerializer
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        return success_response(
            data={
                "root": "",
                "directories": _list_media_directories(),
            }
        )


class AdminMediaUploadAPIView(APIView):
    serializer_class = EmptySerializer
    permission_classes = [permissions.IsAdminUser]
    parser_classes = [MultiPartParser, FormParser]

    @staticmethod
    def _normalize_upload_path_for_collection(raw_path: str) -> str:
        path = (raw_path or "").strip().replace("\\", "/").strip("/")
        lowered = path.lower()
        if lowered in {
            "",
            "temp/uploads/collection-cover",
            "uploads/collection-cover",
            "temp/uploads/collection",
            "uploads/collection",
        }:
            return "temp/collection"
        return path

    def post(self, request):
        upload_file = request.FILES.get("file")
        if upload_file is None:
            return error_response(message="请上传 file 文件", code=400)
        if upload_file.size > MEDIA_UPLOAD_MAX_BYTES:
            return error_response(message="单个文件大小不能超过 5MB", code=400, status_code=status.HTTP_400_BAD_REQUEST)

        requested_path = self._normalize_upload_path_for_collection(str(request.data.get("path", "")))
        try:
            target_dir, normalized = _resolve_media_path(requested_path)
        except ValueError as exc:
            return error_response(message=str(exc), code=400, status_code=status.HTTP_400_BAD_REQUEST)

        target_dir.mkdir(parents=True, exist_ok=True)
        preferred_name = str(request.data.get("filename") or "").strip()
        safe_name = Path(preferred_name).name if preferred_name else (Path(upload_file.name).name or "upload.bin")
        overwrite = _bool_from_value(request.data.get("overwrite"), default=False)
        destination = target_dir / safe_name if overwrite else _ensure_unique_path(target_dir / safe_name)
        with destination.open("wb") as output:
            for chunk in upload_file.chunks():
                output.write(chunk)

        rel_path = f"{normalized}/{destination.name}" if normalized else destination.name
        return success_response(
            data={
                "name": destination.name,
                "url": _build_media_file_url(rel_path),
                "path": normalized,
            },
            message="uploaded",
        )


class AdminMediaRenameAPIView(APIView):
    serializer_class = EmptySerializer
    permission_classes = [permissions.IsAdminUser]

    def post(self, request):
        requested_path = request.data.get("path", "")
        old_name = str(request.data.get("old_name") or "").strip()
        new_name = str(request.data.get("new_name") or "").strip()

        if not old_name or not new_name:
            return error_response(message="old_name 和 new_name 不能为空", code=400)
        if "/" in old_name or "\\" in old_name or "/" in new_name or "\\" in new_name:
            return error_response(message="文件名不允许包含路径分隔符", code=400)

        try:
            target_dir, normalized = _resolve_media_path(requested_path)
        except ValueError as exc:
            return error_response(message=str(exc), code=400, status_code=status.HTTP_400_BAD_REQUEST)

        src = target_dir / old_name
        dst = target_dir / new_name
        if not src.exists():
            return error_response(message="源文件不存在", code=404, status_code=status.HTTP_404_NOT_FOUND)
        if dst.exists():
            return error_response(message="目标文件已存在", code=400)

        src.rename(dst)
        rel_path = f"{normalized}/{dst.name}" if normalized else dst.name
        return success_response(
            data={
                "name": dst.name,
                "url": _build_media_file_url(rel_path),
                "path": normalized,
            },
            message="renamed",
        )
