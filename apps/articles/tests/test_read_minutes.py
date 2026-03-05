from django.test import SimpleTestCase, tag

from apps.articles.services import estimate_read_minutes


@tag("unit")
class EstimateReadMinutesTests(SimpleTestCase):
    def test_should_add_image_reading_time(self) -> None:
        markdown = ("字" * 300) + "\n\n![img](./a.png)"
        self.assertEqual(estimate_read_minutes(markdown), 2)

    def test_should_ignore_images_in_code_blocks(self) -> None:
        markdown = "```markdown\n![img](./a.png)\n```\n"
        self.assertEqual(estimate_read_minutes(markdown), 1)

