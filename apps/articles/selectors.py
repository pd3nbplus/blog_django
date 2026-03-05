from __future__ import annotations

from collections.abc import Iterable
from typing import TypedDict

from django.db.models import Q, QuerySet

from .models import Article, Category


class CategoryTreeNode(TypedDict):
    id: int
    name: str
    slug: str
    level: int
    icon_path: str
    children: list[CategoryTreeNode]


def get_published_articles_queryset() -> QuerySet[Article]:
    return Article.objects.select_related("author", "category").filter(status=Article.Status.PUBLISHED)


def filter_public_articles(
    queryset: QuerySet[Article],
    *,
    keyword: str = "",
    category_id: str | None = None,
) -> QuerySet[Article]:
    q = keyword.strip()
    if q:
        queryset = queryset.filter(Q(title__icontains=q) | Q(summary__icontains=q))
    if category_id:
        queryset = queryset.filter(category_id=category_id)
    return queryset


def filter_admin_articles(
    queryset: QuerySet[Article],
    *,
    keyword: str = "",
    status: str | None = None,
) -> QuerySet[Article]:
    q = keyword.strip()
    if q:
        queryset = queryset.filter(Q(title__icontains=q) | Q(summary__icontains=q) | Q(slug__icontains=q))
    if status:
        queryset = queryset.filter(status=status)
    return queryset


def get_root_categories_queryset() -> QuerySet[Category]:
    return Category.objects.filter(parent__isnull=True).order_by("order", "id")


def get_all_categories_queryset() -> QuerySet[Category]:
    return Category.objects.select_related("parent").all().order_by("order", "id")


def build_category_tree_nodes(categories: Iterable[Category]) -> list[CategoryTreeNode]:
    # Build tree nodes in memory to avoid recursive DB hits when serializing children.
    sorted_categories = sorted(categories, key=lambda item: (item.order, item.id))
    nodes_by_id: dict[int, CategoryTreeNode] = {}

    for category in sorted_categories:
        nodes_by_id[category.id] = {
            "id": category.id,
            "name": category.name,
            "slug": category.slug,
            "level": category.level,
            "icon_path": category.icon_path,
            "children": [],
        }

    roots: list[CategoryTreeNode] = []
    for category in sorted_categories:
        node = nodes_by_id[category.id]
        parent_id = category.parent_id
        if parent_id and parent_id in nodes_by_id:
            parent_node = nodes_by_id[parent_id]
            parent_node["children"].append(node)
            continue
        roots.append(node)

    return roots
