from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from goodnotes_ocr.config import load_env_file
from goodnotes_ocr.errors import GoodnotesOcrError
from goodnotes_ocr.extractor import extract_page_images
from goodnotes_ocr.models import BrowserOptions
from goodnotes_ocr.pages import parse_pages
from goodnotes_ocr.pipeline import analyze_pages
from goodnotes_ocr.vlm import build_vlm_client

try:
    from mcp.server.fastmcp import FastMCP, Image
except ImportError as exc:  # pragma: no cover - import guard for optional runtime dependency
    raise SystemExit(
        "The MCP server requires the `mcp` package. Install requirements.txt first."
    ) from exc


load_env_file()

MCP_TRANSPORT = os.environ.get("MCP_TRANSPORT", "streamable-http")
MCP_HOST = os.environ.get("MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.environ.get("MCP_PORT", "5455"))
MCP_PATH = os.environ.get("MCP_PATH", "/mcp")

mcp = FastMCP(
    "goodnotes-vlm",
    host=MCP_HOST,
    port=MCP_PORT,
    streamable_http_path=MCP_PATH,
)


@mcp.tool()
async def extract_goodnotes(
    url: str,
    pages: int | list[int | str] | str,
    prompt: str | None = None,
    response_schema: dict[str, Any] | None = None,
    just_image: bool = False,
    model: str | None = None,
    ollama_url: str | None = None,
    provider: str | None = None,
    base_url: str | None = None,
) -> Any:
    """Extract GoodNotes page(s), optionally returning MCP image content.

    `provider` selects the VLM backend ('ollama' or 'openai', default from
    VLM_PROVIDER env var). `base_url` overrides the endpoint for whichever
    provider is active; `ollama_url` is kept as an Ollama-specific alias for
    backward compatibility.
    """
    try:
        return await _extract_goodnotes_async(
            url=url,
            pages=pages,
            prompt=prompt,
            response_schema=response_schema,
            just_image=just_image,
            model=model,
            base_url=base_url or ollama_url,
            provider=provider,
        )
    except (GoodnotesOcrError, ValueError) as exc:
        return {"error": str(exc)}


async def _extract_goodnotes_async(
    *,
    url: str,
    pages: int | list[int | str] | str,
    prompt: str | None,
    response_schema: dict[str, Any] | None,
    just_image: bool,
    model: str | None,
    base_url: str | None,
    provider: str | None,
) -> Any:
    page_selectors = parse_pages(pages)
    browser_options = BrowserOptions(
        headless=True,
        timeout_ms=int(os.environ.get("BROWSER_TIMEOUT_MS", "60000")),
        settle_ms=int(os.environ.get("BROWSER_SETTLE_MS", "6000")),
        viewport_width=int(os.environ.get("VIEWPORT_WIDTH", "1500")),
        viewport_height=int(os.environ.get("VIEWPORT_HEIGHT", "1910")),
        max_probe_page=int(os.environ.get("MAX_PROBE_PAGE", "2000")),
    )
    output_dir = Path(os.environ.get("OUTPUT_DIR", "output"))

    if just_image:
        batch = await extract_page_images(
            url,
            page_selectors,
            output_dir=output_dir,
            browser_options=browser_options,
            pdf_dpi=int(os.environ.get("PDF_DPI", "300")),
        )
        images = [Image(path=str(page.image_path)) for page in batch.images]
        return images[0] if len(images) == 1 else images

    if not prompt:
        raise ValueError("`prompt` is required unless `just_image` is true.")
    if response_schema is None:
        raise ValueError("`response_schema` is required when `prompt` is provided.")
    if not isinstance(response_schema, dict):
        raise ValueError("`response_schema` must be a JSON schema object.")

    vlm_client = build_vlm_client(provider=provider, model=model, base_url=base_url)
    results = await analyze_pages(
        source_url=url,
        pages=page_selectors,
        prompt=prompt,
        response_schema=response_schema,
        output_dir=output_dir,
        browser_options=browser_options,
        vlm_client=vlm_client,
        pdf_dpi=int(os.environ.get("PDF_DPI", "300")),
    )
    return [result.to_dict() for result in results]


@mcp.tool()
async def extract_goodnotes_image(
    url: str,
    pages: int | list[int | str] | str,
) -> Any:
    """Extract GoodNotes page image(s) and return MCP Image content."""
    return await extract_goodnotes(url=url, pages=pages, just_image=True)


if __name__ == "__main__":
    mcp.run(transport=MCP_TRANSPORT)
