from django.test import SimpleTestCase, tag

from apps.articles.services import MarkdownRenderer


@tag("unit")
class MarkdownTocMarkerTests(SimpleTestCase):
    def test_lowercase_toc_marker_should_render_toc_block(self) -> None:
        content = "[toc]\n\n# A\n\n## B"
        rendered_html, toc_html = MarkdownRenderer.render(content)
        self.assertIn("class=\"toc\"", rendered_html)
        self.assertIn("A", toc_html)

    def test_at_toc_marker_should_render_toc_block(self) -> None:
        content = "@[toc]\n\n# A\n\n## B"
        rendered_html, toc_html = MarkdownRenderer.render(content)
        self.assertIn("class=\"toc\"", rendered_html)
        self.assertIn("B", toc_html)

    def test_at_toc_marker_with_space_should_render_toc_block(self) -> None:
        content = "@ [toc]\n\n# A\n\n## B"
        rendered_html, toc_html = MarkdownRenderer.render(content)
        self.assertIn("class=\"toc\"", rendered_html)
        self.assertIn("A", toc_html)

    def test_at_toc_marker_with_inner_spaces_should_render_toc_block(self) -> None:
        content = "  @[ toc ]  \n\n# A\n\n## B"
        rendered_html, toc_html = MarkdownRenderer.render(content)
        self.assertIn("class=\"toc\"", rendered_html)
        self.assertIn("B", toc_html)

    def test_inline_toc_marker_should_render_toc_block(self) -> None:
        content = "[toc]\nintro text\n\n# A\n\n## B"
        rendered_html, toc_html = MarkdownRenderer.render(content)
        self.assertIn("class=\"toc\"", rendered_html)
        self.assertIn("A", toc_html)
