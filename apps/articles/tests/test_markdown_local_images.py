from django.test import SimpleTestCase, tag

from apps.articles.services import (
    normalize_source_markdown_path,
    rewrite_markdown_local_refs_for_response,
)


@tag("unit")
class MarkdownLocalImageRewriteTests(SimpleTestCase):
    def test_rewrite_parentheses_path(self) -> None:
        markdown_content = "![x](./img/history()函数与attribute_history()函数.png)"
        rewritten = rewrite_markdown_local_refs_for_response(
            markdown_content,
            "/static/temp/python/量化Quant/JQData 数据获取.md",
        )
        self.assertIn(
            "/static/temp/python/量化Quant/img/history()函数与attribute_history()函数.png",
            rewritten,
        )

    def test_do_not_rewrite_code_block(self) -> None:
        markdown_content = """
```markdown
![x](./img/a.png)
```
"""
        rewritten = rewrite_markdown_local_refs_for_response(
            markdown_content,
            "/static/temp/a/b.md",
        )
        self.assertEqual(markdown_content, rewritten)

    def test_rewrite_legacy_media_articles_path_as_static_temp(self) -> None:
        markdown_content = "![x](./img/a.png)"
        rewritten = rewrite_markdown_local_refs_for_response(
            markdown_content,
            "/media/articles/uploads/20260304/demo.md",
        )
        self.assertIn(
            "/static/temp/uploads/20260304/img/a.png",
            rewritten,
        )

    def test_normalize_source_markdown_path_rejects_media_articles_root(self) -> None:
        with self.assertRaisesRegex(ValueError, "不再支持 /media/articles"):
            normalize_source_markdown_path("/media/articles/uploads/20260304/demo.md")
