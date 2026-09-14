import unittest

from goodnotes_ocr.pages import parse_pages, resolve_pages


class PageParserTests(unittest.TestCase):
    def test_single_page(self):
        self.assertEqual(parse_pages("44"), [44])
        self.assertEqual(parse_pages(44), [44])

    def test_list_and_ranges(self):
        self.assertEqual(parse_pages("1,3-5,5"), [1, 3, 4, 5])

    def test_last_page(self):
        self.assertEqual(parse_pages("last"), ["last"])
        self.assertEqual(parse_pages("1,last"), [1, "last"])
        self.assertEqual(resolve_pages(parse_pages("1,last"), 45), [1, 45])

    def test_last_page_requires_page_count(self):
        with self.assertRaises(ValueError):
            resolve_pages(parse_pages("last"), None)

    def test_invalid_pages(self):
        with self.assertRaises(ValueError):
            parse_pages("0")
        with self.assertRaises(ValueError):
            parse_pages("5-3")


if __name__ == "__main__":
    unittest.main()
