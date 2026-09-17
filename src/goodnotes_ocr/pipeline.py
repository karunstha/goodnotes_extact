from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from goodnotes_ocr.extractor import extract_page_images
from goodnotes_ocr.models import BrowserOptions, VlmPageResult
from goodnotes_ocr.pages import PageSelector
from goodnotes_ocr.vlm import OllamaVisionClient


async def analyze_pages(
    *,
    source_url: str,
    pages: list[PageSelector],
    prompt: str,
    response_schema: dict[str, Any],
    output_dir: Path,
    browser_options: BrowserOptions,
    vlm_client: OllamaVisionClient,
    pdf_dpi: int = 300,
) -> list[VlmPageResult]:
    batch = await extract_page_images(
        source_url,
        pages,
        output_dir=output_dir,
        browser_options=browser_options,
        pdf_dpi=pdf_dpi,
    )

    results: list[VlmPageResult] = []
    for image in batch.images:
        result = await asyncio.to_thread(
            vlm_client.analyze_image,
            image.image_path,
            prompt,
            response_schema,
        )
        results.append(
            VlmPageResult(
                source_url=source_url,
                page=image.page,
                page_count=batch.page_count,
                image_path=image.image_path,
                model=vlm_client.model,
                result=result,
            )
        )
    return results
