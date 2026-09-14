from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from goodnotes_ocr.config import load_env_file
from goodnotes_ocr.errors import GoodnotesOcrError
from goodnotes_ocr.extractor import extract_page_images
from goodnotes_ocr.image_results import image_batch_to_dicts
from goodnotes_ocr.models import BrowserOptions
from goodnotes_ocr.pages import parse_pages
from goodnotes_ocr.pipeline import analyze_pages
from goodnotes_ocr.vlm import DEFAULT_MODEL, DEFAULT_OLLAMA_URL, OllamaVisionClient

try:
    from mcp.server.fastmcp import FastMCP, Image
except ImportError as exc:  # pragma: no cover - import guard for optional runtime dependency
    raise SystemExit(
        "The MCP server requires the `mcp` package. Install requirements.txt first."
    ) from exc


load_env_file()

MCP_TRANSPORT = os.environ.get("MCP_TRANSPORT", "stdio")
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
def extract_goodnotes(
    url: str,
    pages: int | list[int | str] | str,
    prompt: str | None = None,
    just_image: bool = False,
    model: str | None = None,
    ollama_url: str | None = None,
) -> Any:
    """Extract GoodNotes page(s), optionally returning MCP image content."""
    try:
        return asyncio.run(
            _extract_goodnotes_async(
                url=url,
                pages=pages,
                prompt=prompt,
                just_image=just_image,
                model=model,
                ollama_url=ollama_url,
            )
        )
    except (GoodnotesOcrError, ValueError) as exc:
        return {"error": str(exc)}


async def _extract_goodnotes_async(
    *,
    url: str,
    pages: int | list[int | str] | str,
    prompt: str | None,
    just_image: bool,
    model: str | None,
    ollama_url: str | None,
) -> Any:
    page_selectors = parse_pages(pages)
    browser_options = BrowserOptions(
        headless=True,
        timeout_ms=int(os.environ.get("BROWSER_TIMEOUT_MS", "60000")),
        settle_ms=int(os.environ.get("BROWSER_SETTLE_MS", "2000")),
        viewport_width=int(os.environ.get("VIEWPORT_WIDTH", "1500")),
        viewport_height=int(os.environ.get("VIEWPORT_HEIGHT", "2200")),
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

    vlm_client = OllamaVisionClient(
        base_url=ollama_url or os.environ.get("OLLAMA_URL", DEFAULT_OLLAMA_URL),
        model=model or os.environ.get("OLLAMA_MODEL", DEFAULT_MODEL),
        timeout_seconds=int(os.environ.get("VLM_TIMEOUT_SECONDS", "120")),
    )
    results = await analyze_pages(
        source_url=url,
        pages=page_selectors,
        prompt=prompt,
        output_dir=output_dir,
        browser_options=browser_options,
        vlm_client=vlm_client,
        pdf_dpi=int(os.environ.get("PDF_DPI", "300")),
    )
    return [result.to_dict() for result in results]


@mcp.tool()
def extract_goodnotes_image(
    url: str,
    pages: int | list[int | str] | str,
) -> Any:
    """Extract GoodNotes page image(s) and return MCP Image content."""
    return extract_goodnotes(url=url, pages=pages, just_image=True)


@mcp.tool()
def extract_goodnotes_image_metadata(
    url: str,
    pages: int | list[int | str] | str,
) -> list[dict[str, Any]] | dict[str, str]:
    """Extract page image(s) and return paths/metadata instead of image content."""
    try:
        batch = asyncio.run(
            extract_page_images(
                url,
                parse_pages(pages),
                output_dir=Path(os.environ.get("OUTPUT_DIR", "output")),
                browser_options=BrowserOptions(
                    headless=True,
                    timeout_ms=int(os.environ.get("BROWSER_TIMEOUT_MS", "60000")),
                    settle_ms=int(os.environ.get("BROWSER_SETTLE_MS", "2000")),
                    viewport_width=int(os.environ.get("VIEWPORT_WIDTH", "1500")),
                    viewport_height=int(os.environ.get("VIEWPORT_HEIGHT", "2200")),
                    max_probe_page=int(os.environ.get("MAX_PROBE_PAGE", "2000")),
                ),
                pdf_dpi=int(os.environ.get("PDF_DPI", "300")),
            )
        )
        return image_batch_to_dicts(batch)
    except (GoodnotesOcrError, ValueError) as exc:
        return {"error": str(exc)}


if __name__ == "__main__":
    mcp.run(transport=MCP_TRANSPORT)
