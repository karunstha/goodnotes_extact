"""List the checkboxes on a GoodNotes page and tick one in red ink.

Listing works on the anonymous share link. Ticking draws on the page, so it needs a
signed-in session (BrowserOptions.storage_state). Nothing here calls a model.
"""
from __future__ import annotations

import io
from dataclasses import replace
from typing import Any

from PIL import Image

from goodnotes_ocr.browser import PAGE_RECT_SCRIPT, GoodnotesBrowser
from goodnotes_ocr.checkboxes import Checkbox, find_checkboxes, ink_masks
from goodnotes_ocr.models import BrowserOptions
from goodnotes_ocr.pages import PageSelector

TOOLBAR_BOTTOM = 110  # CSS px: the floating pen toolbar covers the page above this when signed in
PRESET_RED = 5        # index of red in the 3x5 pen colour grid

# Box-relative. Drawn backwards, from clear paper above-right down to the corner and up the short leg:
# a stroke that starts inside a filled box is flattened into a straight line (or selects the box).
CHECKMARK = ((1.25, -0.25), (0.40, 0.82), (0.18, 0.48))
SLASH_STARTS = ((1.40, -0.40), (1.15, -0.60), (0.90, -0.70), (0.60, -0.75))  # box-relative, above the box
SLASH_END = (0.22, 0.84)

# Overlays that cover part of the page in an anonymous session.
HIDE_OVERLAYS = """
() => {
  for (const b of document.querySelectorAll("button")) {
    const t = (b.innerText || "").trim();
    if (t === "Accept all" || t === "Continue in browser") {
      let el = b;
      for (let i = 0; i < 6 && el.parentElement && el.parentElement !== document.body; i++) el = el.parentElement;
      el.style.display = "none";
    }
  }
}
"""
# The app keeps its toolbar state in localStorage; read the active tool and pen colour from there.
PEN_STATE = """() => {
  const tb = JSON.parse(localStorage.getItem("toolbarState") || "{}");
  const cfg = tb.pen && tb.pen.colorConfig;
  const c = cfg && cfg.previewColors[cfg.selectedPreviewIndex].color;
  return {tool: tb.tool, rgb: c ? [c.r, c.g, c.b].map(v => Math.round(v * 255)) : null};
}"""
# Main toolbar buttons, left to right: lasso, writing tools, eraser, ...
MAIN_TOOLS = """() => [...document.querySelectorAll("button.toolButton")]
  .map(b => b.getBoundingClientRect()).filter(r => r.y < 40 && r.width > 0)
  .sort((a, b) => a.x - b.x).map(r => ({x: r.x + r.width / 2, y: r.y + r.height / 2}))"""
# The pen colour swatches in the floating toolbar, and the preset grid that opens under them.
# The buttons carry no ids or labels, so they are found by size and position.
SWATCHES = """() => [...document.querySelectorAll("button")].map(b => b.getBoundingClientRect())
  .filter(r => Math.round(r.width) === 38 && Math.round(r.height) === 38 && r.y > 40 && r.y < 330)
  .map(r => ({x: r.x + r.width / 2, y: r.y + r.height / 2}))
  .sort((a, b) => a.y - b.y || a.x - b.x)"""


def _is_red(rgb) -> bool:
    return bool(rgb) and rgb[0] > 200 and rgb[1] < 80 and rgb[2] < 80


def _page_only(shot: Image.Image, rect: dict, scale: float, signed_in: bool) -> Image.Image:
    """Blank everything that isn't notebook page, so toolbars can't be mistaken for ink."""
    out = Image.new("RGB", shot.size, "white")
    top = max(rect["y"], TOOLBAR_BOTTOM) if signed_in else rect["y"]
    box = (int(rect["x"] * scale), int(top * scale),
           int((rect["x"] + rect["width"]) * scale), int((rect["y"] + rect["height"]) * scale))
    out.paste(shot.crop(box), box[:2])
    return out


async def _shot(browser: GoodnotesBrowser) -> Image.Image:
    return Image.open(io.BytesIO(await browser.page.screenshot())).convert("RGB")


async def _resolve_page(browser: GoodnotesBrowser, url: str, page: PageSelector) -> int:
    if page != "last":
        return int(page)
    count = await browser.discover_page_count(url)
    if not count:
        raise ValueError("Cannot resolve 'last' because page count is unknown.")
    return count


async def _open_page(browser: GoodnotesBrowser, url: str, page: int, signed_in: bool) -> tuple[Image.Image, dict]:
    """Load the page and return (page-only screenshot, page rect). Retries the occasional blank render."""
    opts = browser.options
    for _ in range(3):
        await browser.goto_page(url, page)
        await browser._try_make_page_fit()
        await browser.page.wait_for_timeout(opts.settle_ms)
        await browser.page.evaluate(HIDE_OVERLAYS)
        rect = await browser.page.evaluate(PAGE_RECT_SCRIPT)
        shot = _page_only(await _shot(browser), rect, opts.device_scale_factor, signed_in)
        if ink_masks(shot)[0].sum() > 500:  # a blank render has no ink at all
            break
    return shot, rect


async def list_checkboxes(url: str, page: PageSelector, options: BrowserOptions) -> dict[str, Any]:
    """Checkboxes on a page, top to bottom, with whether each is ticked. Read-only and anonymous."""
    async with GoodnotesBrowser(replace(options, storage_state=None)) as browser:
        number = await _resolve_page(browser, url, page)
        shot, _ = await _open_page(browser, url, number, signed_in=False)
    boxes = find_checkboxes(shot, scale=options.device_scale_factor)
    return {"page": number, "count": len(boxes), "checkboxes": [{"n": b.n, "ticked": b.ticked} for b in boxes]}


async def _select_red_pen(page) -> dict:
    """Make the active tool a red pen. GoodNotes remembers both choices on the account."""
    state = await page.evaluate(PEN_STATE)
    if state["tool"] != "pen":
        tools = await page.evaluate(MAIN_TOOLS)
        if len(tools) < 2:
            return state
        await page.mouse.click(tools[1]["x"], tools[1]["y"])
        await page.wait_for_timeout(1200)
        state = await page.evaluate(PEN_STATE)
    if state["tool"] != "pen" or _is_red(state["rgb"]):
        return state  # clicking an already-selected preset would open its editor instead
    row = await page.evaluate(SWATCHES)
    if not row:
        return state
    current = row[0]  # the selected swatch is first in the row
    await page.mouse.click(current["x"], current["y"])
    await page.wait_for_timeout(1200)
    grid = [s for s in await page.evaluate(SWATCHES) if s["y"] > current["y"] + 30]
    if len(grid) != 15:
        await page.keyboard.press("Escape")
        return state
    await page.mouse.click(grid[PRESET_RED]["x"], grid[PRESET_RED]["y"])
    await page.wait_for_timeout(1200)
    return await page.evaluate(PEN_STATE)


async def _stylus_stroke(page, pts: list[tuple[float, float]], step_ms: int = 14) -> None:
    """Drag through pts as a stylus. The canvas inks every point of a stylus stroke, where a
    mouse drag becomes one straight line from press to release."""
    cdp = await page.context.new_cdp_session(page)

    def send(kind: str, x: float, y: float, buttons: int):
        return cdp.send("Input.dispatchMouseEvent", {
            "type": kind, "x": x, "y": y, "button": "left", "buttons": buttons,
            "clickCount": 1, "pointerType": "pen", "force": 0.5})

    await cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": pts[0][0], "y": pts[0][1], "pointerType": "pen"})
    await send("mousePressed", *pts[0], 1)
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        for i in range(1, 16):
            await send("mouseMoved", x0 + (x1 - x0) * i / 15, y0 + (y1 - y0) * i / 15, 1)
            await page.wait_for_timeout(step_ms)
    await send("mouseReleased", *pts[-1], 0)
    await cdp.detach()


async def _mouse_stroke(page, start: tuple[float, float], end: tuple[float, float], ms: int = 600) -> None:
    """A slow mouse drag: one straight line from start to end."""
    await page.mouse.move(*start)
    await page.mouse.down()
    await page.wait_for_timeout(60)
    for i in range(1, 31):
        await page.mouse.move(start[0] + (end[0] - start[0]) * i / 30, start[1] + (end[1] - start[1]) * i / 30)
        await page.wait_for_timeout(ms // 30)
    await page.wait_for_timeout(60)
    await page.mouse.up()


async def tick_checkbox(url: str, page: PageSelector, n: int, count: int, options: BrowserOptions) -> dict[str, Any]:
    """Draw a red checkmark in the n-th checkbox (top to bottom) of the page.

    count is how many tasks the caller's list has for this page; if the page shows a different
    number of boxes the two lists don't line up and nothing is drawn.
    """
    if not options.storage_state:
        return {"status": "no_session", "detail": "ticking needs a signed-in session; set GOODNOTES_STORAGE_STATE"}
    s = options.device_scale_factor
    async with GoodnotesBrowser(options) as browser:
        pg = browser.page
        number = await _resolve_page(browser, url, page)
        shot, rect = await _open_page(browser, url, number, signed_in=True)
        if await pg.get_by_role("button", name="Read Only").count():
            return {"status": "session_expired", "detail": "page opened Read Only; the saved GoodNotes session needs refreshing"}
        boxes = find_checkboxes(shot, scale=s)
        if len(boxes) != count:
            return {"status": "count_mismatch", "detail": f"page has {len(boxes)} checkboxes, caller's list has {count}"}
        if not 1 <= n <= count:
            return {"status": "not_found", "detail": f"page has {count} checkboxes"}
        box = boxes[n - 1]
        if box.ticked:
            return {"status": "already_ticked", "page": number, "n": n}

        pen = await _select_red_pen(pg)
        if pen["tool"] != "pen" or not _is_red(pen["rgb"]):
            return {"status": "failed", "detail": f"toolbar is {pen}, not a red pen; nothing drawn"}

        def css(fx: float, fy: float) -> tuple[float, float]:  # box-relative -> CSS px
            return (box.x0 + fx * box.w) / s, (box.y0 + fy * box.h) / s

        ink, red_before = ink_masks(shot)
        # Fallback slash: a mouse press on or right next to a box selects it, so start on clear
        # paper above it. (Not from the left: that margin is the comment gutter.)
        slash_start = None
        for f in SLASH_STARTS:
            x, y = (int(c * s) for c in css(*f))
            r = int(8 * s)
            if y - r > TOOLBAR_BOTTOM * s and not ink[y - r:y + r, x - r:x + r].any():
                slash_start = css(*f)
                break

        pad = int(0.8 * max(box.w, box.h))
        region = (slice(max(0, box.y0 - pad), box.y1 + pad), slice(max(0, box.x0 - pad), box.x1 + pad))

        async def new_red():
            return ink_masks(_page_only(await _shot(browser), rect, s, True))[1] & ~red_before

        async def attempt(draw, top_limit: float) -> tuple[str, str]:
            """Draw, then judge the new red ink. Returns (verdict, detail); cleans up unless 'ok'."""
            await draw()
            await pg.wait_for_timeout(1500)
            drawn = await new_red()
            inside = drawn[region].sum()
            outside = drawn.sum() - inside
            ys, _ = drawn.nonzero()
            low, high = ((ys.max() - box.y0) / box.h, (ys.min() - box.y0) / box.h) if len(ys) else (0.0, 0.0)
            selected = (await pg.evaluate(PEN_STATE))["tool"] != "pen"
            if selected or inside < 30:
                await pg.keyboard.press("Escape")  # drops a selection and returns to the pen
                await pg.wait_for_timeout(500)
                return "no_ink", "the page did not take the stroke as ink; nothing was drawn"
            # The mark must run from the top of the box (or above it) down into its lower half.
            if outside < 20 and inside >= 0.01 * box.w * box.h and low > 0.6 and high < top_limit:
                return "ok", ""
            await pg.keyboard.press("Control+z")
            await pg.wait_for_timeout(1000)
            left = int((await new_red()).sum())
            return "wrong", (
                f"stroke landed wrong (inside={int(inside)}px, outside={int(outside)}px, "
                f"reaches {high:.0%} to {low:.0%} down the box); "
                + ("undone" if left < 20 else f"UNDO DID NOT CLEAR IT ({left}px left)")
            )

        mark = "check"
        verdict, detail = await attempt(lambda: _stylus_stroke(pg, [css(*f) for f in CHECKMARK]), top_limit=0.3)
        if verdict == "no_ink" and slash_start is not None:
            mark = "slash"
            verdict, detail = await attempt(lambda: _mouse_stroke(pg, slash_start, css(*SLASH_END)), top_limit=0.0)
        if verdict != "ok":
            return {"status": "failed", "detail": detail}

        await pg.wait_for_timeout(6000)  # let the stroke sync before reloading
        shot2, _ = await _open_page(browser, url, number, signed_in=True)
        boxes2 = find_checkboxes(shot2, scale=s)
        if len(boxes2) == count and boxes2[n - 1].ticked:
            return {"status": "ok", "page": number, "n": n, "mark": mark}
        return {"status": "not_saved", "page": number, "n": n, "mark": mark,
                "detail": "the mark was drawn but is missing after a reload"}
