from django.test import SimpleTestCase, tag

from apps.articles.services import html_to_markdown


@tag("unit")
class HtmlToMarkdownTests(SimpleTestCase):
    def test_convert_basic_structure(self) -> None:
        html = """
        <h1>Title</h1>
        <p>Hello <strong>World</strong></p>
        <ul><li>One</li><li>Two</li></ul>
        <p><a href="https://example.com">link</a></p>
        """
        markdown = html_to_markdown(html)

        self.assertIn("# Title", markdown)
        self.assertIn("Hello **World**", markdown)
        self.assertIn("- One", markdown)
        self.assertIn("- Two", markdown)
        self.assertIn("[link](https://example.com)", markdown)

    def test_convert_code_block(self) -> None:
        html = "<pre><code>print('hello')</code></pre>"
        markdown = html_to_markdown(html)
        self.assertIn("```", markdown)
        self.assertIn("print('hello')", markdown)
