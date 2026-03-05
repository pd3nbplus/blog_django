import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Category",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=120)),
                ("slug", models.SlugField(max_length=160, unique=True)),
                ("level", models.PositiveSmallIntegerField(db_index=True, default=1)),
                ("icon_path", models.CharField(blank=True, max_length=255)),
                ("order", models.IntegerField(default=0)),
                (
                    "parent",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="children",
                        to="articles.category",
                    ),
                ),
            ],
            options={
                "ordering": ["order", "id"],
            },
        ),
        migrations.CreateModel(
            name="Article",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("title", models.CharField(max_length=255)),
                ("slug", models.SlugField(max_length=255, unique=True)),
                ("summary", models.TextField(blank=True)),
                ("markdown_content", models.TextField()),
                ("source_markdown_path", models.CharField(blank=True, max_length=255)),
                ("cover_path", models.CharField(blank=True, max_length=255)),
                (
                    "status",
                    models.CharField(
                        choices=[("draft", "Draft"), ("published", "Published"), ("archived", "Archived")],
                        db_index=True,
                        default="draft",
                        max_length=20,
                    ),
                ),
                ("view_count", models.PositiveIntegerField(default=0)),
                ("is_pinned", models.BooleanField(default=False)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("legacy_post_id", models.PositiveIntegerField(blank=True, null=True, unique=True)),
                (
                    "author",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="articles", to=settings.AUTH_USER_MODEL),
                ),
                (
                    "category",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="articles",
                        to="articles.category",
                    ),
                ),
            ],
            options={
                "ordering": ["-is_pinned", "-published_at", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="Comment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("author_name", models.CharField(max_length=100)),
                ("author_email", models.EmailField(max_length=254)),
                ("content", models.TextField()),
                ("is_approved", models.BooleanField(default=False)),
                (
                    "article",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="comments", to="articles.article"),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="category",
            constraint=models.UniqueConstraint(fields=("parent", "name"), name="uniq_category_parent_name"),
        ),
        migrations.AddIndex(
            model_name="article",
            index=models.Index(fields=["status", "-created_at"], name="idx_status_created"),
        ),
        migrations.AddIndex(
            model_name="article",
            index=models.Index(fields=["category", "-created_at"], name="idx_category_created"),
        ),
        migrations.AddIndex(
            model_name="article",
            index=models.Index(fields=["slug"], name="idx_article_slug"),
        ),
    ]
