from typing import Any

from django.contrib.auth.models import User
from rest_framework import serializers

from .models import Article, Category, Collection, Comment
from .services import (
    MarkdownRenderer,
    normalize_source_markdown_path,
    rewrite_markdown_local_refs_for_response,
)


class UserBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username"]


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "slug", "level", "parent", "icon_path", "order"]


class CategoryTreeSerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "level", "icon_path", "children"]

    def get_children(self, obj) -> list[dict]:
        queryset = obj.children.all().order_by("order", "id")
        return CategoryTreeSerializer(queryset, many=True).data


class ArticleListSerializer(serializers.ModelSerializer):
    author = UserBriefSerializer(read_only=True)
    category = CategorySerializer(read_only=True)

    class Meta:
        model = Article
        fields = [
            "id",
            "title",
            "slug",
            "summary",
            "cover_path",
            "author",
            "category",
            "status",
            "view_count",
            "read_minutes",
            "published_at",
            "created_at",
            "updated_at",
        ]

class ArticleDetailSerializer(ArticleListSerializer):
    markdown_content = serializers.SerializerMethodField()
    rendered_html = serializers.SerializerMethodField()
    toc = serializers.SerializerMethodField()

    class Meta(ArticleListSerializer.Meta):
        fields = ArticleListSerializer.Meta.fields + ["markdown_content", "rendered_html", "toc", "source_markdown_path"]

    def get_markdown_content(self, obj) -> str:
        resolve_links = self.context.get("resolve_markdown_links", False)
        if not resolve_links:
            return obj.markdown_content
        return rewrite_markdown_local_refs_for_response(obj.markdown_content, obj.source_markdown_path)

    def get_rendered_html(self, obj) -> str:
        markdown_content = self.get_markdown_content(obj)
        html, _ = MarkdownRenderer.render(markdown_content)
        return html

    def get_toc(self, obj) -> str:
        markdown_content = self.get_markdown_content(obj)
        _, toc = MarkdownRenderer.render(markdown_content)
        return toc


class ArticleWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Article
        fields = [
            "id",
            "title",
            "slug",
            "summary",
            "markdown_content",
            "source_markdown_path",
            "cover_path",
            "author",
            "category",
            "status",
            "is_pinned",
            "published_at",
        ]
        read_only_fields = ["id"]
        extra_kwargs: dict[str, dict[str, list[Any]]] = {
            "slug": {"validators": []},
        }

    def validate_markdown_content(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("markdown_content 不能为空")
        return value

    def validate_slug(self, value):
        slug = (value or "").strip()
        if not slug:
            raise serializers.ValidationError("slug 不能为空")
        queryset = Article.objects.filter(slug=slug)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("slug 已存在，请更换")
        return slug

    def validate_source_markdown_path(self, value):
        try:
            return normalize_source_markdown_path(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc


class CollectionListSerializer(serializers.ModelSerializer):
    article_count = serializers.IntegerField(read_only=True)
    total_views = serializers.IntegerField(read_only=True)

    class Meta:
        model = Collection
        fields = [
            "id",
            "name",
            "slug",
            "summary",
            "cover_path",
            "is_pinned",
            "order",
            "article_count",
            "total_views",
            "created_at",
            "updated_at",
        ]


class CollectionDetailSerializer(CollectionListSerializer):
    article_ids = serializers.SerializerMethodField()

    class Meta(CollectionListSerializer.Meta):
        fields = CollectionListSerializer.Meta.fields + ["article_ids"]

    def get_article_ids(self, obj) -> list[int]:
        return list(obj.articles.values_list("id", flat=True))


class CollectionWriteSerializer(serializers.ModelSerializer):
    article_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        allow_empty=True,
        write_only=True,
    )

    class Meta:
        model = Collection
        fields = [
            "id",
            "name",
            "slug",
            "summary",
            "cover_path",
            "is_pinned",
            "order",
            "article_ids",
        ]
        read_only_fields = ["id"]
        extra_kwargs = {
            "slug": {"required": False, "allow_blank": True, "validators": []},
        }

    def validate_name(self, value):
        name = (value or "").strip()
        if not name:
            raise serializers.ValidationError("合集名称不能为空")
        queryset = Collection.objects.filter(name=name)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("合集名称已存在")
        return name

    def validate_slug(self, value):
        slug = (value or "").strip()
        if not slug:
            return slug
        queryset = Collection.objects.filter(slug=slug)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("slug 已存在，请更换")
        return slug

    def validate_article_ids(self, value):
        article_ids = list(dict.fromkeys(value))
        existing_count = Article.objects.filter(id__in=article_ids).count()
        if existing_count != len(article_ids):
            raise serializers.ValidationError("存在无效文章 ID")
        return article_ids

    def create(self, validated_data):
        article_ids = validated_data.pop("article_ids", [])
        collection = Collection.objects.create(**validated_data)
        if article_ids:
            collection.articles.set(Article.objects.filter(id__in=article_ids))
        return collection

    def update(self, instance, validated_data):
        article_ids = validated_data.pop("article_ids", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        if article_ids is not None:
            instance.articles.set(Article.objects.filter(id__in=article_ids))
        return instance


class CommentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Comment
        fields = ["id", "article", "author_name", "author_email", "content", "is_approved", "created_at"]
        read_only_fields = ["id", "created_at", "is_approved"]


class AdminCategoryWriteSerializer(serializers.ModelSerializer):
    parent = serializers.PrimaryKeyRelatedField(queryset=Category.objects.all(), required=False, allow_null=True)
    slug = serializers.CharField(required=False, allow_blank=True)
    order = serializers.IntegerField(required=False)
    icon_file = serializers.ImageField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "parent", "order", "icon_path", "icon_file"]
        read_only_fields = ["id", "icon_path"]
        validators: list[Any] = []

    def validate_name(self, value):
        name = (value or "").strip()
        if not name:
            raise serializers.ValidationError("分类名称不能为空")
        return name

    def validate(self, attrs):
        parent = attrs.get("parent", self.instance.parent if self.instance else None)
        name = attrs.get("name", self.instance.name if self.instance else "")
        queryset = Category.objects.filter(parent=parent, name=name)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError({"name": "同级分类名称已存在"})
        return attrs


class CommentArticleBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Article
        fields = ["id", "title", "slug"]


class AdminCommentSerializer(serializers.ModelSerializer):
    article = CommentArticleBriefSerializer(read_only=True)

    class Meta:
        model = Comment
        fields = ["id", "article", "author_name", "author_email", "content", "is_approved", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]
