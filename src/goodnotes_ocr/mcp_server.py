from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Awaitable, Callable

from goodnotes_ocr.adding import add_task as _add_task
from goodnotes_ocr.config import load_env_file
from goodnotes_ocr.errors import GoodnotesOcrError
from goodnotes_ocr.extractor import extract_page_images
from goodnotes_ocr.models import BrowserOptions
from goodnotes_ocr.pages import parse_pages
from goodnotes_ocr.pipeline import analyze_pages
from goodnotes_ocr.ticking import list_checkboxes as _list_checkboxes
from goodnotes_ocr.ticking import tick_checkbox as _tick_checkbox
from goodnotes_ocr.vlm import build_vlm_client

try:
    from mcp.server.fastmcp import FastMCP, Image
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
except ImportError as exc:  # pragma: no cover - import guard for optional runtime dependency
    raise SystemExit(
        "The MCP server requires the `mcp` package. Install requirements.txt first."
    ) from exc


load_env_file()

MCP_TRANSPORT = os.environ.get("MCP_TRANSPORT", "streamable-http")
MCP_HOST = os.environ.get("MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.environ.get("MCP_PORT", "5455"))
MCP_PATH = os.environ.get("MCP_PATH", "/mcp")
# After this many browser calls in a row end in a Playwright timeout, the server exits so the
# container's restart policy brings it back fresh. 0 turns it off.
BROWSER_STALL_RESTART = int(os.environ.get("BROWSER_STALL_RESTART", "3"))

_stalls = 0

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
    return await _guarded(lambda: _extract_goodnotes_async(
        url=url,
        pages=pages,
        prompt=prompt,
        response_schema=response_schema,
        just_image=just_image,
        model=model,
        base_url=base_url or ollama_url,
        provider=provider,
    ))


async def _guarded(call: Callable[[], Awaitable[Any]]) -> Any:
    """Run one browser tool call, turning errors into {"error"} and counting timeouts in a row."""
    global _stalls
    try:
        result = await call()
    except PlaywrightTimeoutError as exc:
        _stalls += 1
        if BROWSER_STALL_RESTART and _stalls >= BROWSER_STALL_RESTART:
            print(f"{_stalls} browser timeouts in a row; exiting so the server restarts", file=sys.stderr)
            asyncio.get_running_loop().call_later(1, os._exit, 75)
            return {"error": f"{exc} ({_stalls} timeouts in a row: the server is restarting, retry in ~30s)"}
        return {"error": str(exc)}
    except (GoodnotesOcrError, ValueError) as exc:
        _stalls = 0
        return {"error": str(exc)}
    _stalls = 0
    return result


def _browser_options(*, extract: bool = False) -> BrowserOptions:
    # OCR reads are downscaled to VLM_MAX_IMAGE_DIMENSION anyway, so they can render at a lower
    # device scale (EXTRACT_DEVICE_SCALE_FACTOR). Drawing tools find boxes from pixels tuned at
    # DEVICE_SCALE_FACTOR (2.0), so they keep that.
    scale_env = "EXTRACT_DEVICE_SCALE_FACTOR" if extract else "DEVICE_SCALE_FACTOR"
    return BrowserOptions(
        device_scale_factor=float(os.environ.get(scale_env) or os.environ.get("DEVICE_SCALE_FACTOR", "2.0")),
        headless=True,
        timeout_ms=int(os.environ.get("BROWSER_TIMEOUT_MS", "60000")),
        settle_ms=int(os.environ.get("BROWSER_SETTLE_MS", "6000")),
        viewport_width=int(os.environ.get("VIEWPORT_WIDTH", "1500")),
        viewport_height=int(os.environ.get("VIEWPORT_HEIGHT", "1910")),
        max_probe_page=int(os.environ.get("MAX_PROBE_PAGE", "2000")),
        storage_state=os.environ.get("GOODNOTES_STORAGE_STATE") or None,
    )


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
    browser_options = _browser_options(extract=True)
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


def _single_page(page: int | str) -> int | str:
    selectors = parse_pages(page)
    if len(selectors) != 1:
        raise ValueError("`page` must be a single page number or 'last'.")
    return selectors[0]


@mcp.tool()
async def list_checkboxes(url: str, page: int | str = "last") -> Any:
    """List the hand-drawn checkboxes on one GoodNotes page, top to bottom.

    Returns {"page", "count", "checkboxes": [{"n", "ticked"}]}. A box is ticked when it has
    red ink in it. Read-only; found from pixels, no model call.
    """
    return await _guarded(lambda: _list_checkboxes(url, _single_page(page), _browser_options()))


@mcp.tool()
async def tick_checkbox(url: str, page: int | str, n: int, count: int) -> Any:
    """Draw a red checkmark in the n-th checkbox (1-based, top to bottom) of one GoodNotes page.

    `count` is the number of tasks in the caller's own list for that page; if the page shows a
    different number of checkboxes nothing is drawn (status "count_mismatch"). Returns
    {"status": "ok" | "already_ticked" | "count_mismatch" | "not_found" | "session_expired" |
    "no_session" | "not_saved" | "failed", ...}. Needs GOODNOTES_STORAGE_STATE (a Playwright
    storage-state file for a signed-in GoodNotes session with edit access). No model call.
    """
    return await _guarded(lambda: _tick_checkbox(url, _single_page(page), n, count, _browser_options()))


@mcp.tool()
async def add_task(url: str, page: int | str, text: str, count: int) -> Any:
    """Append a new unticked checkbox with typed text below the last checkbox of one GoodNotes page.

    `count` is the number of tasks in the caller's own list for that page; if the page shows a
    different number of checkboxes nothing is added (status "count_mismatch"). On "ok" the new
    line is checkbox `n` of `count`. Returns {"status": "ok" | "count_mismatch" | "page_full" |
    "session_expired" | "no_session" | "not_saved" | "failed", ...}. Needs
    GOODNOTES_STORAGE_STATE, like tick_checkbox. No model call.
    """
    return await _guarded(lambda: _add_task(url, _single_page(page), text, count, _browser_options()))


if __name__ == "__main__":
    mcp.run(transport=MCP_TRANSPORT)
