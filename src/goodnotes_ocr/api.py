from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from goodnotes_ocr.config import load_env_file
from goodnotes_ocr.errors import GoodnotesOcrError
from goodnotes_ocr.extractor import extract_page_images
from goodnotes_ocr.image_results import image_batch_to_dicts
from goodnotes_ocr.models import BrowserOptions
from goodnotes_ocr.pages import parse_pages
from goodnotes_ocr.pipeline import analyze_pages
from goodnotes_ocr.vlm import DEFAULT_MODEL, DEFAULT_OLLAMA_URL, OllamaVisionClient


load_env_file()

app = FastAPI(title="GoodNotes VLM Extractor")


class ExtractRequest(BaseModel):
    url: str = Field(..., description="GoodNotes share URL or direct PDF URL.")
    pages: int | list[int | str] | str = Field(
        ...,
        description="Page number, list, range string like '1,3-5', or 'last'.",
    )
    prompt: str | None = Field(None, description="Prompt describing the JSON extraction task.")
    response_schema: dict[str, Any] | None = Field(
        None,
        description="Ollama JSON schema passed as the chat `format` for VLM extraction.",
    )
    just_image: bool = Field(False, description="Return extracted page image(s) without a VLM call.")
    model: str | None = Field(None, description="Ollama model name.")
    ollama_url: str | None = Field(None, description="Ollama base URL.")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/extract")
async def extract(request: ExtractRequest) -> Any:
    try:
        pages = parse_pages(request.pages)
        browser_options = BrowserOptions(
            headless=True,
            timeout_ms=int(os.environ.get("BROWSER_TIMEOUT_MS", "60000")),
            settle_ms=int(os.environ.get("BROWSER_SETTLE_MS", "6000")),
            viewport_width=int(os.environ.get("VIEWPORT_WIDTH", "1500")),
            viewport_height=int(os.environ.get("VIEWPORT_HEIGHT", "1910")),
            max_probe_page=int(os.environ.get("MAX_PROBE_PAGE", "2000")),
        )
        vlm_client = OllamaVisionClient(
            base_url=request.ollama_url
            or os.environ.get("OLLAMA_URL", DEFAULT_OLLAMA_URL),
            model=request.model or os.environ.get("OLLAMA_MODEL", DEFAULT_MODEL),
            timeout_seconds=int(os.environ.get("VLM_TIMEOUT_SECONDS", "120")),
        )
        output_dir = Path(os.environ.get("OUTPUT_DIR", "output"))
        if request.just_image:
            batch = await extract_page_images(
                request.url,
                pages,
                output_dir=output_dir,
                browser_options=browser_options,
                pdf_dpi=int(os.environ.get("PDF_DPI", "300")),
            )
            if len(batch.images) == 1:
                return FileResponse(batch.images[0].image_path, media_type="image/png")
            return image_batch_to_dicts(batch)

        if not request.prompt:
            raise ValueError("`prompt` is required unless `just_image` is true.")
        if request.response_schema is None:
            raise ValueError("`response_schema` is required when `prompt` is provided.")

        results = await analyze_pages(
            source_url=request.url,
            pages=pages,
            prompt=request.prompt,
            response_schema=request.response_schema,
            output_dir=output_dir,
            browser_options=browser_options,
            vlm_client=vlm_client,
            pdf_dpi=int(os.environ.get("PDF_DPI", "300")),
        )
        return [result.to_dict() for result in results]
    except (GoodnotesOcrError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Timed out during extraction.") from exc
