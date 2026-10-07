"""Append a task line (a hand-style checkbox plus typed text) to a GoodNotes to-do page.

Like ticking, this draws on the page, so it needs a signed-in session. Nothing here calls a model.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from goodnotes_ocr.browser import GoodnotesBrowser
from goodnotes_ocr.checkboxes import find_checkboxes, ink_masks
from goodnotes_ocr.models import BrowserOptions
from goodnotes_ocr.pages import PageSelector
from goodnotes_ocr.ticking import (
    MAIN_TOOLS, SWATCHES, TOOLBAR_BOTTOM, _open_page, _page_only, _resolve_page, _shot, _stylus_stroke,
)

PRESET_BLUE = 10      # index of the box blue in the 3x5 pen colour grid
TEXT_TOOL = 3         # position of the text tool among the main toolbar buttons
MAX_TEXT = 80
# A click with the text tool opens an editor whose first glyph sits this far left of the click,
# vertically centred on it (CSS px).
TEXT_CLICK_DX = 22
TEXT_GAP = 34         # CSS px between the box and the text
BOTTOM_MARGIN = 30    # CSS px kept clear above the bottom edge of the page
MAX_UNDOS = 12

TOOLBAR = """() => {
  const tb = JSON.parse(localStorage.getItem("toolbarState") || "{}");
  const cfg = tb.pen && tb.pen.colorConfig;
  const rgb = c => [c.r, c.g, c.b].map(v => Math.round(v * 255));
  return {tool: tb.tool, selected: cfg ? cfg.selectedPreviewIndex : null,
          colors: cfg ? cfg.previewColors.map(p => rgb(p.color)) : []};
}"""
# The text format bar can stay floating over the page after its text is deselected. It is page
# chrome, not ink: hide any small floating group of buttons below the toolbars before measuring.
HIDE_POPUPS = """(top) => {
  const area = innerWidth * innerHeight;
  for (const b of document.querySelectorAll("button")) {
    const r = b.getBoundingClientRect();
    if (r.width === 0 || r.y < top) continue;
    let el = b;
    while (el.parentElement && el.parentElement !== document.body) {
      const p = el.parentElement.getBoundingClientRect();
      if (p.width * p.height > 0.1 * area) break;
      el = el.parentElement;
    }
    const e = el.getBoundingClientRect();
    if (e.width * e.height <= 0.1 * area) el.style.visibility = "hidden";
  }
}"""
EDITING = "() => !!(document.activeElement && document.activeElement.isContentEditable)"


def _is_blue(rgb) -> bool:
    return bool(rgb) and rgb[0] < 60 and 90 < rgb[1] < 160 and rgb[2] > 220


async def _select_blue_pen(page) -> bool:
    """Make the active tool a blue pen. GoodNotes remembers both choices on the account."""
    state = await page.evaluate(TOOLBAR)
    if state["tool"] != "pen":
        tools = await page.evaluate(MAIN_TOOLS)
        if len(tools) < 2:
            return False
        await page.mouse.click(tools[1]["x"], tools[1]["y"])
        await page.wait_for_timeout(1200)
        state = await page.evaluate(TOOLBAR)
    if state["tool"] != "pen" or state["selected"] is None:
        return False
    if _is_blue(state["colors"][state["selected"]]):
        return True
    row = await page.evaluate(SWATCHES)
    if len(row) < len(state["colors"]):
        return False
    quick = [i for i, c in enumerate(state["colors"]) if _is_blue(c)]
    if quick:  # one of the quick swatches is already blue: clicking an unselected swatch selects it
        await page.mouse.click(row[quick[0]]["x"], row[quick[0]]["y"])
    else:      # clicking the selected swatch opens the preset grid under the row
        current = row[state["selected"]]
        await page.mouse.click(current["x"], current["y"])
        await page.wait_for_timeout(1200)
        grid = [s for s in await page.evaluate(SWATCHES) if s["y"] > current["y"] + 30]
        if len(grid) != 15:
            await page.keyboard.press("Escape")
            return False
        await page.mouse.click(grid[PRESET_BLUE]["x"], grid[PRESET_BLUE]["y"])
    await page.wait_for_timeout(1200)
    state = await page.evaluate(TOOLBAR)
    return state["tool"] == "pen" and _is_blue(state["colors"][state["selected"]])


def _aligned(now: np.ndarray, before: np.ndarray, strip) -> np.ndarray:
    """now, shifted the pixel or two the page can move between screenshots, to line up with before."""
    d = min(((dy, dx) for dy in range(-4, 5) for dx in range(-4, 5)),
            key=lambda d: int((np.roll(now[strip], d, (0, 1)) ^ before[strip]).sum()))
    return np.roll(now, d, (0, 1))


async def add_task(url: str, page: PageSelector, text: str, count: int, options: BrowserOptions) -> dict[str, Any]:
    """Append a new unticked checkbox with typed text below the last checkbox of the page.

    count is how many tasks the caller's list has for this page; if the page shows a different
    number of boxes the two lists don't line up and nothing is added.
    """
    if not options.storage_state:
        return {"status": "no_session", "detail": "adding needs a signed-in session; set GOODNOTES_STORAGE_STATE"}
    text = " ".join(text.split())
    if not text or len(text) > MAX_TEXT:
        return {"status": "failed", "detail": f"text must be 1 to {MAX_TEXT} characters on one line; nothing added"}
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
        if not boxes:
            return {"status": "failed", "detail": "the page has no checkbox to line a new one up with; nothing added"}
        if not await _select_blue_pen(pg) and not await _select_blue_pen(pg):
            return {"status": "failed", "detail": "could not select a blue pen; nothing added"}
        await pg.wait_for_timeout(500)
        shot = _page_only(await _shot(browser), rect, s, True)
        boxes = find_checkboxes(shot, scale=s)
        if len(boxes) != count:
            return {"status": "failed", "detail": "the page changed while it was being read; nothing added"}
        ink_before = ink_masks(shot)[0] | ink_masks(shot)[1]

        # The new line copies the list's own layout: the usual box size, left edge and line gap.
        w = int(np.median([b.w for b in boxes]))
        h = int(min(np.median([b.h for b in boxes]), w))
        x0 = int(np.median([b.x0 for b in boxes]))
        gaps = [b.y0 - a.y1 for a, b in zip(boxes, boxes[1:])]
        y0 = boxes[-1].y1 + int(max(np.median(gaps) if gaps else 0.8 * h, 0.5 * h))
        x1, y1 = x0 + w, y0 + h
        page_right = int((rect["x"] + rect["width"]) * s)
        page_bottom = int((rect["y"] + rect["height"] - BOTTOM_MARGIN) * s)
        pad = int(0.25 * h)
        band = (slice(y0 - pad, y1 + pad), slice(max(0, x0 - pad), page_right))
        if y1 + pad > page_bottom:
            return {"status": "page_full", "detail": "no room below the last checkbox; nothing added"}
        if y0 / s < TOOLBAR_BOTTOM or ink_before[band].any():
            return {"status": "failed", "detail": "the line below the last checkbox already has ink on it; nothing added"}
        strip = (slice(None), slice(max(0, x0 - 100), x1 + 600))

        async def inks() -> tuple[np.ndarray, np.ndarray]:
            """(all ink now, lined up with before; the checkboxes now), with nothing selected."""
            if not await pg.evaluate(EDITING):
                await pg.evaluate(HIDE_POPUPS, TOOLBAR_BOTTOM)
            now = _page_only(await _shot(browser), rect, s, True)
            masks = ink_masks(now)
            return _aligned(masks[0] | masks[1], ink_before, strip), find_checkboxes(now, scale=s)

        async def undo_all() -> bool:
            """Undo until the page is back to how it was. Undo history is per session, so this
            can't reach anything older than this call."""
            for _ in range(MAX_UNDOS):
                if await pg.evaluate(EDITING):
                    await pg.keyboard.press("Escape")
                    await pg.wait_for_timeout(600)
                    continue
                if int(((await inks())[0] ^ ink_before).sum()) <= 400:
                    break
                await pg.keyboard.press("Control+z")
                await pg.wait_for_timeout(1000)
            clean = int(((await inks())[0] ^ ink_before).sum()) <= 400
            await pg.wait_for_timeout(5000)  # let the undo sync before the browser closes
            return clean

        async def fail(why: str) -> dict[str, Any]:
            clean = await undo_all()
            return {"status": "failed", "detail": why + ("; undone" if clean else "; UNDO DID NOT CLEAR IT")}

        # The box: four straight stylus strokes that overshoot each corner a little so they close.
        e = 2.0
        l, t, r, b = x0 / s, y0 / s, x1 / s, y1 / s
        for a, z in (((l - e, t), (r + e, t)), ((r, t - e), (r, b + e)), ((r + e, b), (l - e, b)), ((l, b + e), (l, t - e))):
            await _stylus_stroke(pg, [a, z])
            await pg.wait_for_timeout(350)
        await pg.wait_for_timeout(1200)
        ink_now, boxes_now = await inks()
        outside = (ink_now ^ ink_before)
        outside[band] = False
        if len(boxes_now) != count + 1 or boxes_now[-1].ticked or abs(boxes_now[-1].y0 - y0) > h or int(outside.sum()) > 400:
            return await fail(f"the new box did not come out as a checkbox ({len(boxes_now)} boxes found, {int(outside.sum())}px changed elsewhere)")
        new = boxes_now[-1]

        # The text: typed with the text tool, starting just right of the box and centred on it.
        tools = await pg.evaluate(MAIN_TOOLS)
        if len(tools) <= TEXT_TOOL:
            return await fail("text tool not found")
        await pg.mouse.click(tools[TEXT_TOOL]["x"], tools[TEXT_TOOL]["y"])
        await pg.wait_for_timeout(1200)
        if (await pg.evaluate(TOOLBAR))["tool"] != "text":
            return await fail("text tool did not activate")
        await pg.mouse.click(new.x1 / s + TEXT_GAP + TEXT_CLICK_DX, (new.y0 + new.y1) / 2 / s)
        await pg.wait_for_timeout(1200)
        if not await pg.evaluate(EDITING):
            return await fail("the text editor did not open")
        await pg.keyboard.type(text, delay=30)
        await pg.wait_for_timeout(600)
        # Escape leaves the editor but keeps the text selected (lasso tool, format bar over the
        # page); switching back to the pen drops the selection.
        await pg.keyboard.press("Escape")
        await pg.wait_for_timeout(700)
        if (await pg.evaluate(TOOLBAR))["tool"] != "pen":
            await pg.mouse.click(tools[1]["x"], tools[1]["y"])
            await pg.wait_for_timeout(1200)
        ink_now, boxes_now = await inks()
        outside = (ink_now ^ ink_before)
        outside[band] = False
        typed = ink_now[y0 - pad:y1 + pad, x1 + int(TEXT_GAP * s / 2):page_right]
        if len(boxes_now) != count + 1 or int(outside.sum()) > 400 or int(typed.sum()) < 150:
            return await fail(f"the text did not land beside the box ({int(typed.sum())}px of text, {int(outside.sum())}px changed elsewhere)")

        await pg.wait_for_timeout(6000)  # let the edits sync before reloading
        shot2, _ = await _open_page(browser, url, number, signed_in=True)
        boxes2 = find_checkboxes(shot2, scale=s)
        masks2 = ink_masks(shot2)
        saved = _aligned(masks2[0] | masks2[1], ink_before, strip)[y0 - pad:y1 + pad, x1 + int(TEXT_GAP * s / 2):page_right]
        if len(boxes2) == count + 1 and int(saved.sum()) >= 150:
            return {"status": "ok", "page": number, "n": count + 1, "count": count + 1}
        return {"status": "not_saved", "page": number, "detail": "the line was added but is missing after a reload"}
