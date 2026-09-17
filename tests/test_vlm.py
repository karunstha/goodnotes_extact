import unittest

from goodnotes_ocr.vlm import _parse_json_response, _response_text


class VlmTests(unittest.TestCase):
    def test_parse_valid_json(self):
        self.assertEqual(_parse_json_response('{"date": "2026-09-12"}'), {"date": "2026-09-12"})

    def test_parse_invalid_json_returns_json_wrapper(self):
        result = _parse_json_response("not json")
        self.assertEqual(result["raw_response"], "not json")
        self.assertIn("parse_error", result)

    def test_response_text_falls_back_to_thinking(self):
        result = _response_text(
            {
                "response": "",
                "thinking": '{"text_content": "August 2 2026"}',
            }
        )
        self.assertEqual(result, '{"text_content": "August 2 2026"}')


if __name__ == "__main__":
    unittest.main()
