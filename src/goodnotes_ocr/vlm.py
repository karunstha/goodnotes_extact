from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from goodnotes_ocr.errors import VlmError


DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3.2-vision"

PROMPT_TEMPLATE = """You are analyzing one rendered GoodNotes notebook page image.

Return only valid JSON. Do not include Markdown, comments, or prose outside the
JSON. If the requested value is not visible on the page, use null.

User extraction request:
{prompt}
"""


class OllamaVisionClient:
    def __init__(
        self,
        *,
        base_url: str = DEFAULT_OLLAMA_URL,
        model: str = DEFAULT_MODEL,
        timeout_seconds: int = 120,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    def analyze_image(self, image_path: Path, prompt: str) -> Any:
        payload = {
            "model": self.model,
            "prompt": PROMPT_TEMPLATE.format(prompt=prompt),
            "images": [_image_to_base64(image_path)],
            "stream": False,
            "format": "json",
        }
        response = self._post_json("/api/generate", payload)
        raw_text = _response_text(response)
        return _parse_json_response(raw_text)

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise VlmError(f"Ollama HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise VlmError(f"Could not reach Ollama at {self.base_url}: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise VlmError("Ollama returned non-JSON HTTP response.") from exc


def _image_to_base64(image_path: Path) -> str:
    return base64.b64encode(image_path.read_bytes()).decode("ascii")


def _response_text(response: dict[str, Any]) -> str:
    for key in ("response", "thinking"):
        value = response.get(key)
        if isinstance(value, str) and value.strip():
            return value
    if isinstance(response.get("response"), str):
        return response["response"]
    raise VlmError(
        "Ollama response did not include a string `response` or `thinking` field."
    )


def _parse_json_response(raw_text: str) -> Any:
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        return {
            "raw_response": raw_text,
            "parse_error": "Model response was not valid JSON.",
        }
