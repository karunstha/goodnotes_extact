import unittest

from goodnotes_ocr.vlm import _parse_json_response


class VlmTests(unittest.TestCase):
    def test_parse_valid_json(self):
        self.assertEqual(_parse_json_response('{"date": "2026-09-12"}'), {"date": "2026-09-12"})

    def test_parse_invalid_json_returns_json_wrapper(self):
        result = _parse_json_response("not json")
        self.assertEqual(result["raw_response"], "not json")
        self.assertIn("parse_error", result)


if __name__ == "__main__":
    unittest.main()
