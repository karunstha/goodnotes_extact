import unittest

from goodnotes_ocr.vlm import _chat_payload, _parse_json_response, _response_text


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

    def test_response_text_reads_chat_message_content(self):
        result = _response_text(
            {
                "message": {
                    "role": "assistant",
                    "content": '{"date": "August 2 2026", "tasks": [], "ambiguous": []}',
                }
            }
        )
        self.assertIn("August 2 2026", result)

    def test_chat_payload_uses_schema_format(self):
        payload = _chat_payload(
            model="gemma4:12b-64k",
            prompt="read the contents of this page",
            image_b64="abc123",
            response_schema={"type": "object", "properties": {"text": {"type": "string"}}},
        )
        self.assertEqual(payload["model"], "gemma4:12b-64k")
        self.assertEqual(payload["messages"][0]["images"], ["abc123"])
        self.assertIs(payload["think"], False)
        self.assertIs(payload["stream"], False)
        self.assertIn("read the contents of this page", payload["messages"][0]["content"])
        self.assertEqual(payload["format"], {"type": "object", "properties": {"text": {"type": "string"}}})


if __name__ == "__main__":
    unittest.main()
