from __future__ import annotations

from pathlib import Path

from goodnotes_ocr.browser import GoodnotesBrowser
from goodnotes_ocr.errors import GoodnotesOcrError, PageOutOfRangeError
from goodnotes_ocr.models import BrowserOptions, PageImage, PageImageBatch
from goodnotes_ocr.pages import PageSelector, resolve_pages
from goodnotes_ocr.pdf import download_pdf, page_count, render_page
from goodnotes_ocr.urls import is_probably_pdf_url, safe_output_stem, without_fragment


async def extract_page_images(
    source_url: str,
    pages: list[PageSelector],
    *,
    output_dir: Path,
    browser_options: BrowserOptions,
    pdf_dpi: int = 300,
) -> PageImageBatch:
    if not pages:
        raise GoodnotesOcrError("At least one page is required.")

    output_dir.mkdir(parents=True, exist_ok=True)
    if is_probably_pdf_url(source_url):
        return _extract_pdf_pages(
            source_url,
            pages,
            output_dir=output_dir,
            pdf_dpi=pdf_dpi,
        )

    async with GoodnotesBrowser(browser_options) as browser:
        count = await browser.discover_page_count(source_url)
        resolved_pages = resolve_pages(pages, count)
        if count is not None:
            too_large = [page for page in resolved_pages if page > count]
            if too_large:
                raise PageOutOfRangeError(
                    f"Page {too_large[0]} is outside document range 1-{count}."
                )

        images: list[PageImage] = []
        for page in resolved_pages:
            image_path = await browser.screenshot_page(
                without_fragment(source_url),
                page,
                output_dir / f"page-{page}.png",
            )
            images.append(PageImage(page=page, image_path=image_path))

    return PageImageBatch(
        source_url=source_url,
        page_count=count,
        images=tuple(images),
        used_pdf=False,
    )


def _extract_pdf_pages(
    source_url: str,
    pages: list[PageSelector],
    *,
    output_dir: Path,
    pdf_dpi: int,
) -> PageImageBatch:
    pdf_path = download_pdf(source_url, output_dir / f"{safe_output_stem(source_url)}.pdf")
    count = page_count(pdf_path)
    resolved_pages = resolve_pages(pages, count)
    too_large = [page for page in resolved_pages if page > count]
    if too_large:
        raise PageOutOfRangeError(f"Page {too_large[0]} is outside document range 1-{count}.")

    images = tuple(
        PageImage(
            page=page,
            image_path=render_page(
                pdf_path,
                page,
                output_dir / f"page-{page}.png",
                dpi=pdf_dpi,
            ),
        )
        for page in resolved_pages
    )
    return PageImageBatch(
        source_url=source_url,
        page_count=count,
        images=images,
        used_pdf=True,
    )
