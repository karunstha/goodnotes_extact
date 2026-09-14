from __future__ import annotations

import re
from urllib.parse import ParseResult, urlparse, urlunparse

PAGE_FRAGMENT_RE = re.compile(r"^page-(?P<page>[1-9][0-9]*)$", re.IGNORECASE)


def parse_page_fragment(url: str) -> int | None:
    """Return a page number from a URL fragment like '#page-44'."""
    match = PAGE_FRAGMENT_RE.match(urlparse(url).fragment)
    if not match:
        return None
    return int(match.group("page"))


def with_page_fragment(url: str, page: int) -> str:
    """Return the same URL with a GoodNotes '#page-N' fragment."""
    if page < 1:
        raise ValueError("page must be 1 or greater")
    parsed = urlparse(url)
    return urlunparse(_replace_fragment(parsed, f"page-{page}"))


def without_fragment(url: str) -> str:
    return urlunparse(_replace_fragment(urlparse(url), ""))


def is_probably_pdf_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.path.lower().endswith(".pdf")


def safe_output_stem(url: str) -> str:
    parsed = urlparse(url)
    last_path = parsed.path.rstrip("/").split("/")[-1] or "document"
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", last_path).strip(".-")
    if cleaned.lower().endswith(".pdf"):
        cleaned = cleaned[:-4]
    return cleaned or "document"


def _replace_fragment(parsed: ParseResult, fragment: str) -> ParseResult:
    return parsed._replace(fragment=fragment)
