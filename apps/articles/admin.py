from django.contrib import admin

from .models import Article, Category, Collection, Comment


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "level", "parent", "order")
    list_filter = ("level",)
    search_fields = ("name", "slug")


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "author", "category", "status", "view_count", "created_at")
    list_filter = ("status", "category")
    search_fields = ("title", "slug", "summary")


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("id", "article", "author_name", "is_approved", "created_at")
    list_filter = ("is_approved",)
    search_fields = ("author_name", "author_email", "content")


@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "is_pinned", "order", "created_at", "updated_at")
    list_filter = ("is_pinned",)
    search_fields = ("name", "slug", "summary")
    filter_horizontal = ("articles",)
