import unittest
from pathlib import Path

from goodnotes_ocr.extractor import _request_output_dir


class ExtractorTests(unittest.TestCase):
    def test_request_output_dir_is_unique(self):
        first = _request_output_dir(
            Path("output"),
            "https://web.goodnotes.com/s/notebook",
            [3],
        )
        second = _request_output_dir(
            Path("output"),
            "https://web.goodnotes.com/s/notebook",
            [3],
        )

        self.assertNotEqual(first, second)
        self.assertEqual(first.parent, Path("output/requests"))
        self.assertIn("notebook-pages-3-", first.name)

    def test_request_output_dir_summarizes_long_page_lists(self):
        path = _request_output_dir(
            Path("output"),
            "https://web.goodnotes.com/s/notebook",
            [1, 2, 3, 4, 5, 6, 7],
        )

        self.assertIn("notebook-pages-1-2-3-4-5-6-plus-", path.name)


if __name__ == "__main__":
    unittest.main()
