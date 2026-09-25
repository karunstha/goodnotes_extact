from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

from goodnotes_ocr.errors import VlmError


DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3.2-vision"
DEFAULT_OPENAI_BASE_URL = "http://localhost:8080/v1"
DEFAULT_OPENAI_MODEL = "default"
# Full-resolution GoodNotes screenshots (2800x3600+) push some VLM backends
# (e.g. llama.cpp Qwen-VL style vision encoders) to tens of thousands of image
# tokens, which can exceed the compute-buffer VRAM a tightly-configured
# context leaves free. Downscaling the copy we send over the wire (the saved
# screenshot on disk is untouched) keeps token count sane without losing
# handwriting legibility.
DEFAULT_MAX_IMAGE_DIMENSION = 1600

PROMPT_TEMPLATE = """You are analyzing one rendered GoodNotes notebook page image.

Return only valid JSON. Do not include Markdown, comments, or prose outside the
JSON. If the requested value is not visible on the page, use null. Use the
provided response schema.

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

    def analyze_image(
        self,
        image_path: Path,
        prompt: str,
        response_schema: dict[str, Any],
    ) -> Any:
        payload = _chat_payload(
            model=self.model,
            prompt=prompt,
            image_b64=_image_to_base64(image_path),
            response_schema=response_schema,
        )
        response = self._post_json("/api/chat", payload)
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


class OpenAIVisionClient:
    """Vision client for any OpenAI-compatible `/chat/completions` server
    (llama.cpp's `llama-server`, vLLM, LM Studio, etc.), for cases where the
    vision model isn't served through Ollama."""

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_OPENAI_BASE_URL,
        model: str = DEFAULT_OPENAI_MODEL,
        api_key: str = "none",
        timeout_seconds: int = 120,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def analyze_image(
        self,
        image_path: Path,
        prompt: str,
        response_schema: dict[str, Any],
    ) -> Any:
        image_b64 = _image_to_base64(image_path)
        try:
            response = self._post_json(
                "/chat/completions",
                _openai_chat_payload(
                    model=self.model,
                    prompt=prompt,
                    image_b64=image_b64,
                    response_schema=response_schema,
                    use_schema=True,
                ),
            )
        except VlmError:
            # Some OpenAI-compatible servers reject a strict json_schema
            # response_format. Retry once relying on the prompt's own
            # "return only valid JSON" instruction instead.
            response = self._post_json(
                "/chat/completions",
                _openai_chat_payload(
                    model=self.model,
                    prompt=prompt,
                    image_b64=image_b64,
                    response_schema=response_schema,
                    use_schema=False,
                ),
            )
        raw_text = _openai_response_text(response)
        return _parse_json_response(raw_text)

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise VlmError(f"OpenAI-compatible endpoint HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise VlmError(
                f"Could not reach OpenAI-compatible endpoint at {self.base_url}: {exc.reason}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise VlmError("OpenAI-compatible endpoint returned non-JSON HTTP response.") from exc


def build_vlm_client(
    *,
    provider: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    timeout_seconds: int | None = None,
) -> "OllamaVisionClient | OpenAIVisionClient":
    """Construct the configured VLM client. Reads VLM_PROVIDER/OLLAMA_*/OPENAI_*
    from the environment for whichever field isn't passed explicitly."""
    resolved_provider = (provider or os.environ.get("VLM_PROVIDER", "ollama")).strip().lower()
    resolved_timeout = (
        timeout_seconds
        if timeout_seconds is not None
        else int(os.environ.get("VLM_TIMEOUT_SECONDS", "120"))
    )

    if resolved_provider == "openai":
        return OpenAIVisionClient(
            base_url=base_url or os.environ.get("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL),
            model=model or os.environ.get("OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
            api_key=os.environ.get("OPENAI_API_KEY", "none"),
            timeout_seconds=resolved_timeout,
        )
    if resolved_provider == "ollama":
        return OllamaVisionClient(
            base_url=base_url or os.environ.get("OLLAMA_URL", DEFAULT_OLLAMA_URL),
            model=model or os.environ.get("OLLAMA_MODEL", DEFAULT_MODEL),
            timeout_seconds=resolved_timeout,
        )
    raise VlmError(f"Unknown VLM_PROVIDER '{resolved_provider}'. Expected 'ollama' or 'openai'.")


def _image_to_base64(image_path: Path) -> str:
    max_dim = int(
        os.environ.get("VLM_MAX_IMAGE_DIMENSION", str(DEFAULT_MAX_IMAGE_DIMENSION))
    )
    with Image.open(image_path) as img:
        if max(img.size) <= max_dim:
            return base64.b64encode(image_path.read_bytes()).decode("ascii")
        img = img.convert("RGB")
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("ascii")


def _chat_payload(
    *,
    model: str,
    prompt: str,
    image_b64: str,
    response_schema: dict[str, Any],
) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": PROMPT_TEMPLATE.format(prompt=prompt),
                "images": [image_b64],
            }
        ],
        "think": False,
        "stream": False,
        "format": response_schema,
    }


def _response_text(response: dict[str, Any]) -> str:
    message = response.get("message")
    if isinstance(message, dict):
        for key in ("content", "thinking"):
            value = message.get(key)
            if isinstance(value, str) and value.strip():
                return value
        if isinstance(message.get("content"), str):
            return message["content"]

    for key in ("response", "thinking"):
        value = response.get(key)
        if isinstance(value, str) and value.strip():
            return value
    if isinstance(response.get("response"), str):
        return response["response"]
    raise VlmError(
        "Ollama response did not include assistant content, `response`, or `thinking`."
    )


def _openai_chat_payload(
    *,
    model: str,
    prompt: str,
    image_b64: str,
    response_schema: dict[str, Any],
    use_schema: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT_TEMPLATE.format(prompt=prompt)},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                    },
                ],
            }
        ],
        "stream": False,
    }
    if use_schema:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "extraction_result",
                "schema": response_schema,
                "strict": True,
            },
        }
    return payload


def _openai_response_text(response: dict[str, Any]) -> str:
    choices = response.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return content
    raise VlmError(
        "OpenAI-compatible response did not include choices[0].message.content."
    )


def _parse_json_response(raw_text: str) -> Any:
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        return {
            "raw_response": raw_text,
            "parse_error": "Model response was not valid JSON.",
        }
