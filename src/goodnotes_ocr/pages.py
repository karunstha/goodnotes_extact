from __future__ import annotations

from collections.abc import Iterable

LAST_PAGE = "last"
PageSelector = int | str


def parse_pages(value: str | int | Iterable[int | str]) -> list[PageSelector]:
    """Parse pages from an int, an iterable, or strings like '1,3-5,last'."""
    if isinstance(value, int):
        pages = [value]
    elif isinstance(value, str):
        pages = _parse_pages_string(value)
    else:
        pages = [_coerce_page_selector(page) for page in value]

    if not pages:
        raise ValueError("At least one page is required.")
    numeric_pages = [page for page in pages if isinstance(page, int)]
    if any(page < 1 for page in numeric_pages):
        raise ValueError("Pages must be 1 or greater.")
    return _dedupe_preserving_order(pages)


def resolve_pages(pages: list[PageSelector], page_count: int | None) -> list[int]:
    if LAST_PAGE in pages and page_count is None:
        raise ValueError("Cannot resolve 'last' because page count is unknown.")
    return [page_count if page == LAST_PAGE else int(page) for page in pages]


def _parse_pages_string(value: str) -> list[PageSelector]:
    pages: list[PageSelector] = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if part.lower() == LAST_PAGE:
            pages.append(LAST_PAGE)
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start = int(start_text.strip())
            end = int(end_text.strip())
            if end < start:
                raise ValueError(f"Invalid descending page range: {part}")
            pages.extend(range(start, end + 1))
        else:
            pages.append(int(part))
    return pages


def _coerce_page_selector(value: int | str) -> PageSelector:
    if isinstance(value, int):
        return value
    if value.lower() == LAST_PAGE:
        return LAST_PAGE
    return int(value)


def _dedupe_preserving_order(pages: list[PageSelector]) -> list[PageSelector]:
    seen: set[PageSelector] = set()
    deduped: list[PageSelector] = []
    for page in pages:
        if page in seen:
            continue
        seen.add(page)
        deduped.append(page)
    return deduped
