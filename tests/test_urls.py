import unittest

from goodnotes_ocr.urls import (
    parse_page_fragment,
    safe_output_stem,
    with_page_fragment,
    without_fragment,
)


class UrlTests(unittest.TestCase):
    def test_parse_page_fragment(self):
        self.assertEqual(parse_page_fragment("https://web.goodnotes.com/s/abc#page-44"), 44)
        self.assertIsNone(parse_page_fragment("https://web.goodnotes.com/s/abc#foo"))
        self.assertIsNone(parse_page_fragment("https://web.goodnotes.com/s/abc#page-0"))

    def test_with_page_fragment_replaces_existing_fragment(self):
        url = "https://web.goodnotes.com/s/abc?x=1#page-2"
        self.assertEqual(with_page_fragment(url, 44), "https://web.goodnotes.com/s/abc?x=1#page-44")

    def test_without_fragment(self):
        self.assertEqual(
            without_fragment("https://web.goodnotes.com/s/abc#page-44"),
            "https://web.goodnotes.com/s/abc",
        )

    def test_safe_output_stem(self):
        self.assertEqual(safe_output_stem("https://web.goodnotes.com/s/oXNpvq0N3CcdtJ9KPXkD4Z"), "oXNpvq0N3CcdtJ9KPXkD4Z")
        self.assertEqual(safe_output_stem("https://example.com/path/file.pdf"), "file")


if __name__ == "__main__":
    unittest.main()
