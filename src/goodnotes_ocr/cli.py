from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from goodnotes_ocr.config import load_env_file
from goodnotes_ocr.errors import GoodnotesOcrError
from goodnotes_ocr.extractor import extract_page_images
from goodnotes_ocr.image_results import image_batch_to_dicts
from goodnotes_ocr.models import BrowserOptions
from goodnotes_ocr.pages import parse_pages
from goodnotes_ocr.pipeline import analyze_pages
from goodnotes_ocr.urls import parse_page_fragment
from goodnotes_ocr.vlm import DEFAULT_MODEL, DEFAULT_OLLAMA_URL, OllamaVisionClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract GoodNotes pages and analyze them with an Ollama VLM."
    )
    parser.add_argument("url", help="GoodNotes share URL or direct PDF URL.")
    parser.add_argument(
        "--pages",
        help="Pages to analyze, for example '1', '1,3,5', '2-4', or 'last'.",
    )
    parser.add_argument(
        "--prompt",
        required=False,
        help="Extraction prompt for the vision model. Ask it for the JSON shape you want.",
    )
    parser.add_argument(
        "--just_image",
        "--just-image",
        action="store_true",
        help="Only extract requested page image(s), skipping the VLM call.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(os.environ.get("OUTPUT_DIR", "output")),
        help="Directory for extracted page images.",
    )
    parser.add_argument(
        "--ollama-url",
        default=os.environ.get("OLLAMA_URL", DEFAULT_OLLAMA_URL),
        help="Ollama base URL.",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("OLLAMA_MODEL", DEFAULT_MODEL),
        help="Ollama vision model name.",
    )
    parser.add_argument("--headful", action="store_true", help="Show the browser window.")
    parser.add_argument("--timeout-ms", type=int, default=int(os.environ.get("BROWSER_TIMEOUT_MS", "60000")))
    parser.add_argument("--settle-ms", type=int, default=int(os.environ.get("BROWSER_SETTLE_MS", "6000")))
    parser.add_argument("--max-probe-page", type=int, default=int(os.environ.get("MAX_PROBE_PAGE", "2000")))
    parser.add_argument("--viewport-width", type=int, default=int(os.environ.get("VIEWPORT_WIDTH", "1500")))
    parser.add_argument("--viewport-height", type=int, default=int(os.environ.get("VIEWPORT_HEIGHT", "2200")))
    parser.add_argument("--pdf-dpi", type=int, default=int(os.environ.get("PDF_DPI", "300")))
    parser.add_argument("--vlm-timeout-seconds", type=int, default=int(os.environ.get("VLM_TIMEOUT_SECONDS", "120")))
    return parser


def main(argv: list[str] | None = None) -> int:
    load_env_file()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        results = asyncio.run(run(args))
    except (GoodnotesOcrError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, indent=2), file=sys.stderr)
        return 1

    print(json.dumps(results, indent=2))
    return 0


async def run(args: argparse.Namespace) -> list[dict[str, object]]:
    pages_arg = args.pages or parse_page_fragment(args.url)
    if pages_arg is None:
        raise ValueError("Pass --pages or include a #page-N fragment in the URL.")
    pages = parse_pages(pages_arg)

    browser_options = BrowserOptions(
        headless=not args.headful,
        timeout_ms=args.timeout_ms,
        settle_ms=args.settle_ms,
        viewport_width=args.viewport_width,
        viewport_height=args.viewport_height,
        max_probe_page=args.max_probe_page,
    )
    if args.just_image:
        batch = await extract_page_images(
            args.url,
            pages,
            output_dir=args.out,
            browser_options=browser_options,
            pdf_dpi=args.pdf_dpi,
        )
        return image_batch_to_dicts(batch)

    if not args.prompt:
        raise ValueError("Pass --prompt unless --just_image is set.")

    vlm_client = OllamaVisionClient(
        base_url=args.ollama_url,
        model=args.model,
        timeout_seconds=args.vlm_timeout_seconds,
    )
    results = await analyze_pages(
        source_url=args.url,
        pages=pages,
        prompt=args.prompt,
        output_dir=args.out,
        browser_options=browser_options,
        vlm_client=vlm_client,
        pdf_dpi=args.pdf_dpi,
    )
    return [result.to_dict() for result in results]
