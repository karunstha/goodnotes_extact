import unittest

from goodnotes_ocr.browser import PageMetrics, _current_page_from_text


class BrowserMetricsTests(unittest.TestCase):
    def test_explicit_page_count(self):
        metrics = PageMetrics.from_raw(
            {"totals": [12, 44], "currentPages": [3], "visiblePages": []}
        )
        self.assertEqual(metrics.explicit_page_count, 44)

    def test_unavailable_detection(self):
        metrics = PageMetrics.from_raw(
            {"title": "Goodnotes", "bodyTextSample": "Document unavailable"}
        )
        self.assertTrue(metrics.indicates_unavailable())

    def test_current_page_from_text(self):
        self.assertEqual(_current_page_from_text("Page 44 of 120"), 44)
        self.assertEqual(_current_page_from_text("44 / 120"), 44)
        self.assertIsNone(_current_page_from_text("120 / 44"))


if __name__ == "__main__":
    unittest.main()
