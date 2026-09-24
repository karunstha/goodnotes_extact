import os
import unittest
from unittest import mock

from goodnotes_ocr.vlm import (
    OllamaVisionClient,
    OpenAIVisionClient,
    _chat_payload,
    _openai_chat_payload,
    _openai_response_text,
    _parse_json_response,
    _response_text,
    build_vlm_client,
)


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

    def test_openai_chat_payload_uses_image_url_content(self):
        payload = _openai_chat_payload(
            model="default",
            prompt="read the contents of this page",
            image_b64="abc123",
            response_schema={"type": "object", "properties": {"text": {"type": "string"}}},
            use_schema=True,
        )
        self.assertEqual(payload["model"], "default")
        content = payload["messages"][0]["content"]
        self.assertEqual(content[1]["image_url"]["url"], "data:image/png;base64,abc123")
        self.assertIn("read the contents of this page", content[0]["text"])
        self.assertEqual(payload["response_format"]["json_schema"]["schema"]["type"], "object")

    def test_openai_chat_payload_omits_response_format_without_schema(self):
        payload = _openai_chat_payload(
            model="default",
            prompt="read the contents of this page",
            image_b64="abc123",
            response_schema={"type": "object"},
            use_schema=False,
        )
        self.assertNotIn("response_format", payload)

    def test_openai_response_text_reads_choices(self):
        result = _openai_response_text(
            {"choices": [{"message": {"content": '{"text_content": "hi"}'}}]}
        )
        self.assertEqual(result, '{"text_content": "hi"}')

    def test_build_vlm_client_defaults_to_ollama(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            client = build_vlm_client()
        self.assertIsInstance(client, OllamaVisionClient)

    def test_build_vlm_client_selects_openai_from_env(self):
        env = {
            "VLM_PROVIDER": "openai",
            "OPENAI_BASE_URL": "http://example.internal:8090/v1",
            "OPENAI_MODEL": "bonsai2",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            client = build_vlm_client()
        self.assertIsInstance(client, OpenAIVisionClient)
        self.assertEqual(client.base_url, "http://example.internal:8090/v1")
        self.assertEqual(client.model, "bonsai2")

    def test_build_vlm_client_explicit_args_override_env(self):
        with mock.patch.dict(os.environ, {"VLM_PROVIDER": "ollama"}, clear=True):
            client = build_vlm_client(provider="openai", model="m", base_url="http://x/v1")
        self.assertIsInstance(client, OpenAIVisionClient)
        self.assertEqual(client.model, "m")

    def test_build_vlm_client_unknown_provider_raises(self):
        with mock.patch.dict(os.environ, {"VLM_PROVIDER": "bogus"}, clear=True):
            with self.assertRaises(Exception):
                build_vlm_client()


if __name__ == "__main__":
    unittest.main()
