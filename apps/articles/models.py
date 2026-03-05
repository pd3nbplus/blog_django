from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Category(TimeStampedModel):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=160, unique=True)
    level = models.PositiveSmallIntegerField(default=1, db_index=True)
    parent = models.ForeignKey("self", null=True, blank=True, related_name="children", on_delete=models.SET_NULL)
    icon_path = models.CharField(max_length=255, blank=True)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["parent", "name"], name="uniq_category_parent_name"),
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            seed = slugify(self.name)
            if not seed:
                seed = f"category-{int(timezone.now().timestamp())}"
            self.slug = seed
        super().save(*args, **kwargs)


class Article(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    summary = models.TextField(blank=True)
    markdown_content = models.TextField()
    source_markdown_path = models.CharField(max_length=255, blank=True)
    cover_path = models.CharField(max_length=255, blank=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="articles", on_delete=models.PROTECT)
    category = models.ForeignKey(Category, related_name="articles", null=True, blank=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    view_count = models.PositiveIntegerField(default=0)
    read_minutes = models.PositiveIntegerField(default=1)
    is_pinned = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    legacy_post_id = models.PositiveIntegerField(null=True, blank=True, unique=True)

    class Meta:
        ordering = ["-is_pinned", "-published_at", "-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"], name="idx_status_created"),
            models.Index(fields=["category", "-created_at"], name="idx_category_created"),
            models.Index(fields=["slug"], name="idx_article_slug"),
        ]

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        should_recalculate_read_minutes = self._state.adding or update_fields is None or "markdown_content" in update_fields
        if should_recalculate_read_minutes:
            from .services import estimate_read_minutes

            self.read_minutes = estimate_read_minutes(self.markdown_content)
            if update_fields is not None:
                kwargs["update_fields"] = list({*update_fields, "read_minutes"})

        if not self.slug:
            seed = slugify(self.title)
            if not seed:
                seed = f"article-{int(timezone.now().timestamp())}"
            self.slug = seed
        if self.status == self.Status.PUBLISHED and not self.published_at:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)


class Collection(TimeStampedModel):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=160, unique=True)
    summary = models.TextField(blank=True)
    cover_path = models.CharField(max_length=255, blank=True)
    is_pinned = models.BooleanField(default=False, db_index=True)
    order = models.IntegerField(default=0)
    articles = models.ManyToManyField(Article, related_name="collections", blank=True)

    class Meta:
        ordering = ["-is_pinned", "order", "-updated_at", "-id"]
        indexes = [
            models.Index(fields=["is_pinned", "order"], name="idx_collection_pin"),
            models.Index(fields=["slug"], name="idx_collection_slug"),
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            seed = slugify(self.name)
            if not seed:
                seed = f"collection-{int(timezone.now().timestamp())}"
            self.slug = seed
        super().save(*args, **kwargs)


class Comment(TimeStampedModel):
    article = models.ForeignKey(Article, related_name="comments", on_delete=models.CASCADE)
    author_name = models.CharField(max_length=100)
    author_email = models.EmailField()
    content = models.TextField()
    is_approved = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Comment by {self.author_name} on {self.article_id}"
