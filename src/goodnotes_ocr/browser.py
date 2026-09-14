from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from goodnotes_ocr.errors import DependencyError, PageDiscoveryError
from goodnotes_ocr.models import BrowserOptions
from goodnotes_ocr.urls import with_page_fragment, without_fragment


PAGE_METRICS_SCRIPT = r"""
() => {
  const numberLimit = 100000;
  const totals = [];
  const currentPages = [];
  const visiblePages = [];
  const text = document.body?.innerText || "";
  const addTotal = (value) => {
    const n = Number(value);
    if (Number.isInteger(n) && n >= 1 && n < numberLimit) totals.push(n);
  };
  const addCurrent = (value) => {
    const n = Number(value);
    if (Number.isInteger(n) && n >= 1 && n < numberLimit) currentPages.push(n);
  };
  const addVisible = (value) => {
    const n = Number(value);
    if (Number.isInteger(n) && n >= 1 && n < numberLimit) visiblePages.push(n);
  };

  for (const re of [
    /(?:page|p\.?)?\s*([1-9][0-9]{0,4})\s*(?:of|\/)\s*([1-9][0-9]{0,4})/ig,
    /\b([1-9][0-9]{0,4})\s*\/\s*([1-9][0-9]{0,4})\b/g
  ]) {
    for (const match of text.matchAll(re)) {
      const current = Number(match[1]);
      const total = Number(match[2]);
      if (total >= current) {
        addCurrent(current);
        addTotal(total);
      }
    }
  }

  const attrNames = [
    "id",
    "aria-label",
    "data-page",
    "data-page-number",
    "data-page-index",
    "page",
    "pageid",
    "pageId"
  ];
  for (const el of document.querySelectorAll("[id], [aria-label], [data-page], [data-page-number], [data-page-index], [page], [pageid], [pageId], page-view")) {
    for (const attr of attrNames) {
      const value = el.getAttribute?.(attr);
      if (!value) continue;
      let match = value.match(/(?:^|[^a-z])page[-_\s#]*([1-9][0-9]{0,4})(?:\b|$)/i);
      if (!match) match = value.match(/^(?:page|interaction-layer-page)-([1-9][0-9]{0,4})$/i);
      if (match) addVisible(match[1]);
      if (attr === "data-page-number" || attr === "data-page") {
        const n = Number(value);
        if (Number.isInteger(n)) addVisible(n);
      }
      if (attr === "data-page-index") {
        const n = Number(value);
        if (Number.isInteger(n)) addVisible(n + 1);
      }
    }
  }

  return {
    totals: [...new Set(totals)].sort((a, b) => a - b),
    currentPages: [...new Set(currentPages)].sort((a, b) => a - b),
    visiblePages: [...new Set(visiblePages)].sort((a, b) => a - b),
    title: document.title,
    bodyTextSample: text.slice(0, 2000)
  };
}
"""

PAGE_RECT_SCRIPT = r"""
() => {
  const viewport = { width: window.innerWidth, height: window.innerHeight };
  const candidates = [];
  const selector = [
    "page-view",
    "[id^='page-']",
    "[id^='interaction-layer-page-']",
    "canvas",
    "img",
    "svg"
  ].join(",");

  const visibleArea = (rect) => {
    const left = Math.max(0, rect.left);
    const top = Math.max(0, rect.top);
    const right = Math.min(viewport.width, rect.right);
    const bottom = Math.min(viewport.height, rect.bottom);
    return Math.max(0, right - left) * Math.max(0, bottom - top);
  };

  const addCandidate = (el, weight) => {
    const rect = el.getBoundingClientRect();
    if (!rect || rect.width < 100 || rect.height < 100) return;
    const area = rect.width * rect.height;
    const visible = visibleArea(rect);
    if (visible < 20000) return;
    const style = window.getComputedStyle(el);
    if (style.visibility === "hidden" || style.display === "none") return;
    candidates.push({
      x: Math.max(0, rect.x),
      y: Math.max(0, rect.y),
      width: Math.min(rect.width, viewport.width - Math.max(0, rect.x)),
      height: Math.min(rect.height, viewport.height - Math.max(0, rect.y)),
      area,
      visible,
      tag: el.tagName.toLowerCase(),
      id: el.id || "",
      score: visible + area * weight
    });
  };

  for (const el of document.querySelectorAll(selector)) {
    const tag = el.tagName.toLowerCase();
    if (tag === "page-view") addCandidate(el, 1.0);
    else if (tag === "canvas") {
      const pageParent = el.closest("page-view, [id^='page-'], [id^='interaction-layer-page-']");
      if (pageParent) addCandidate(pageParent, 1.0);
      addCandidate(el, 0.8);
    } else {
      addCandidate(el, 0.3);
    }
  }

  candidates.sort((a, b) => b.score - a.score);
  const best = candidates[0];
  if (best) {
    return {
      x: Math.floor(best.x),
      y: Math.floor(best.y),
      width: Math.floor(best.width),
      height: Math.floor(best.height),
      tag: best.tag,
      id: best.id
    };
  }
  return { x: 0, y: 0, width: viewport.width, height: viewport.height, tag: "viewport", id: "" };
}
"""

SCROLL_BOTTOM_SCRIPT = r"""
() => {
  const elements = [
    document.scrollingElement,
    ...document.querySelectorAll("*")
  ].filter((el) => {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    return /(auto|scroll)/.test(style.overflowY) && el.scrollHeight > el.clientHeight + 50;
  });
  for (const el of elements) {
    el.scrollTop = el.scrollHeight;
  }
  window.scrollTo(0, document.body.scrollHeight);
  return elements.length;
}
"""


@dataclass(frozen=True)
class PageMetrics:
    totals: tuple[int, ...]
    current_pages: tuple[int, ...]
    visible_pages: tuple[int, ...]
    title: str
    body_text_sample: str

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "PageMetrics":
        return cls(
            totals=tuple(raw.get("totals") or ()),
            current_pages=tuple(raw.get("currentPages") or ()),
            visible_pages=tuple(raw.get("visiblePages") or ()),
            title=str(raw.get("title") or ""),
            body_text_sample=str(raw.get("bodyTextSample") or ""),
        )

    @property
    def explicit_page_count(self) -> int | None:
        return max(self.totals) if self.totals else None

    @property
    def visible_max_page(self) -> int | None:
        return max(self.visible_pages) if self.visible_pages else None

    def indicates_unavailable(self) -> bool:
        haystack = f"{self.title}\n{self.body_text_sample}".lower()
        return any(
            phrase in haystack
            for phrase in (
                "not found",
                "unable to load",
                "access denied",
                "document unavailable",
                "no longer available",
            )
        )


class GoodnotesBrowser:
    def __init__(self, options: BrowserOptions | None = None):
        self.options = options or BrowserOptions()
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._pdf_responses: list[tuple[str, bytes]] = []
        self._response_tasks: list[asyncio.Task[None]] = []

    async def __aenter__(self) -> "GoodnotesBrowser":
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise DependencyError(
                "Playwright is required for GoodNotes web links. Run "
                "`python -m pip install -e .` and "
                "`python -m playwright install chromium`."
            ) from exc

        self._playwright = await async_playwright().start()
        try:
            self._browser = await self._playwright.chromium.launch(
                headless=self.options.headless
            )
        except Exception as exc:
            await self._playwright.stop()
            raise DependencyError(
                "Playwright Chromium could not launch. If the browser is not "
                "installed, run `python -m playwright install chromium`. "
                f"Original error: {exc}"
            ) from exc
        self._context = await self._browser.new_context(
            viewport={
                "width": self.options.viewport_width,
                "height": self.options.viewport_height,
            },
            device_scale_factor=self.options.device_scale_factor,
        )
        self._page = await self._context.new_page()
        self._page.on("response", self._queue_pdf_response)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._response_tasks:
            await asyncio.gather(*self._response_tasks, return_exceptions=True)
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    @property
    def page(self):
        if self._page is None:
            raise RuntimeError("GoodnotesBrowser must be used as an async context manager.")
        return self._page

    async def goto_page(self, url: str, page_number: int | None = None) -> PageMetrics:
        target = with_page_fragment(url, page_number) if page_number else url
        await self.page.goto(
            target,
            wait_until="domcontentloaded",
            timeout=self.options.timeout_ms,
        )
        await self._wait_for_viewer()
        return await self.metrics()

    async def discover_page_count(self, url: str) -> int | None:
        metrics = await self.goto_page(without_fragment(url))
        if metrics.explicit_page_count:
            return metrics.explicit_page_count

        await self.page.evaluate(SCROLL_BOTTOM_SCRIPT)
        await self.page.wait_for_timeout(self.options.settle_ms)
        metrics = await self.metrics()
        if metrics.explicit_page_count:
            return metrics.explicit_page_count
        if metrics.visible_max_page and metrics.visible_max_page > 1:
            return metrics.visible_max_page

        return await self._probe_last_page(url)

    async def screenshot_page(self, url: str, page_number: int, output_path: Path) -> Path:
        metrics = await self.goto_page(url, page_number)
        if metrics.indicates_unavailable():
            raise PageDiscoveryError(
                "GoodNotes reported that the shared document is unavailable."
            )

        await self._try_make_page_fit()
        await self.page.wait_for_timeout(self.options.settle_ms)
        rect = await self.page.evaluate(PAGE_RECT_SCRIPT)
        clip = {
            "x": max(0, float(rect["x"])),
            "y": max(0, float(rect["y"])),
            "width": max(1, float(rect["width"])),
            "height": max(1, float(rect["height"])),
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        await self.page.screenshot(path=str(output_path), clip=clip)
        return output_path

    async def save_captured_pdf(self, output_path: Path) -> Path | None:
        if self._response_tasks:
            await asyncio.gather(*self._response_tasks, return_exceptions=True)
        if not self._pdf_responses:
            return None
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(self._pdf_responses[0][1])
        return output_path

    async def metrics(self) -> PageMetrics:
        return PageMetrics.from_raw(await self.page.evaluate(PAGE_METRICS_SCRIPT))

    def _queue_pdf_response(self, response) -> None:
        task = asyncio.create_task(self._capture_pdf_response(response))
        self._response_tasks.append(task)

    async def _capture_pdf_response(self, response) -> None:
        try:
            content_type = response.headers.get("content-type", "")
            url = response.url.lower().split("?", 1)[0]
            if "application/pdf" not in content_type.lower() and not url.endswith(".pdf"):
                return
            body = await response.body()
            if body.startswith(b"%PDF"):
                self._pdf_responses.append((response.url, body))
        except Exception:
            return

    async def _wait_for_viewer(self) -> None:
        try:
            await self.page.wait_for_load_state(
                "networkidle",
                timeout=min(self.options.timeout_ms, 15_000),
            )
        except Exception:
            pass
        try:
            await self.page.wait_for_function(
                r"""
                () => {
                  const text = document.body?.innerText || "";
                  if (/not found|unable to load|access denied|unavailable/i.test(text)) {
                    return true;
                  }
                  const canvas = [...document.querySelectorAll("canvas")]
                    .some((c) => c.width > 200 && c.height > 200);
                  const pageish = document.querySelector(
                    "page-view, [id^='page-'], [id^='interaction-layer-page-']"
                  );
                  return Boolean(canvas || pageish);
                }
                """,
                timeout=self.options.timeout_ms,
            )
        except Exception:
            pass
        await self.page.wait_for_timeout(self.options.settle_ms)

    async def _try_make_page_fit(self) -> None:
        modifier = "Meta" if await self._is_mac() else "Control"
        for key in ("0", "-"):
            try:
                await self.page.keyboard.press(f"{modifier}+{key}")
            except Exception:
                pass

    async def _is_mac(self) -> bool:
        return bool(
            await self.page.evaluate("() => /Mac|iPhone|iPad/.test(navigator.platform)")
        )

    async def _probe_last_page(self, url: str) -> int | None:
        low = 0
        high = 1
        while high <= self.options.max_probe_page:
            exists = await self._page_exists(url, high)
            if exists is None:
                return None
            if not exists:
                break
            low = high
            high *= 2

        if low == 0:
            return None
        if high > self.options.max_probe_page:
            high = self.options.max_probe_page
            if await self._page_exists(url, high):
                return high

        while low + 1 < high:
            mid = (low + high) // 2
            exists = await self._page_exists(url, mid)
            if exists is None:
                return None
            if exists:
                low = mid
            else:
                high = mid
        return low

    async def _page_exists(self, url: str, page_number: int) -> bool | None:
        metrics = await self.goto_page(url, page_number)
        if metrics.indicates_unavailable():
            return False
        explicit_count = metrics.explicit_page_count
        if explicit_count is not None:
            return page_number <= explicit_count
        if page_number in metrics.visible_pages:
            return True
        if page_number in metrics.current_pages:
            return True
        current = _current_page_from_text(metrics.body_text_sample)
        if current is not None:
            return current == page_number
        return None


def _current_page_from_text(text: str) -> int | None:
    for match in re.finditer(
        r"(?:page|p\.?)?\s*([1-9][0-9]{0,4})\s*(?:of|\/)\s*([1-9][0-9]{0,4})",
        text,
        flags=re.IGNORECASE,
    ):
        current = int(match.group(1))
        total = int(match.group(2))
        if current <= total:
            return current
    return None
