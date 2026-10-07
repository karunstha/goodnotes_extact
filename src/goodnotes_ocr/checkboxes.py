"""Find hand-drawn checkboxes in a GoodNotes page screenshot and tell which are ticked in red.

Pure pixel work (numpy + scipy); no model is involved. Coordinates are screenshot pixels.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image
from scipy import ndimage


@dataclass(frozen=True)
class Checkbox:
    n: int  # 1-based, top to bottom
    x0: int
    y0: int
    x1: int
    y1: int
    ticked: bool

    @property
    def w(self) -> int:
        return self.x1 - self.x0

    @property
    def h(self) -> int:
        return self.y1 - self.y0


def ink_masks(img: Image.Image) -> tuple[np.ndarray, np.ndarray]:
    """Return (ink, red) boolean masks. Ink excludes red; template dots/lines are too pale to count."""
    a = np.asarray(img.convert("RGB")).astype(np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    mx, mn = a.max(axis=2), a.min(axis=2)
    red = (r > 150) & (r - g > 90) & (r - b > 90)
    ink = (((mx - mn) > 70) | (mx < 110)) & ~red
    return ink, red


def _corner_gaps(region: np.ndarray) -> list[float]:
    """For each bounding-box corner, how far (0..1 of the box size) the nearest region pixel is."""
    h, w = region.shape
    yy, xx = np.nonzero(region)
    return [
        float(np.min(np.maximum(np.abs(yy - cy) / h, np.abs(xx - cx) / w)))
        for cy, cx in ((0, 0), (0, w - 1), (h - 1, 0), (h - 1, w - 1))
    ]


def _edge_bend(region: np.ndarray) -> float:
    """How curved the region's sides are: 0 for straight sides (any tilt), ~0.03+ for an ellipse."""
    h, w = region.shape
    bends = []
    for prof, size in (
        (region.argmax(axis=1), w),                    # left edge, per row
        (w - 1 - region[:, ::-1].argmax(axis=1), w),   # right edge
        (region.argmax(axis=0), h),                    # top edge, per column
        (h - 1 - region[::-1, :].argmax(axis=0), h),   # bottom edge
    ):
        n = len(prof)
        mid = prof[int(n * 0.15):int(n * 0.85)].astype(float)
        t = np.arange(len(mid))
        resid = mid - np.polyval(np.polyfit(t, mid, 1), t)
        bends.append(float(np.sqrt(np.mean(resid ** 2))) / size)
    return float(np.median(bends))


def find_checkboxes(img: Image.Image, scale: float = 2.0) -> list[Checkbox]:
    """Checkboxes on the page, numbered top to bottom.

    scale is screenshot pixels per CSS pixel; the size limits below are in CSS pixels.

    A checkbox is an enclosed empty region with straight sides and corners. Letters like O
    or D also enclose a region, so candidates must be box-sized, straight-sided, cornered,
    and lined up in one column. A box counts as ticked when it has red ink inside.
    """
    ink, red = ink_masks(img)
    g = int(4 * scale) | 1
    # Hand-drawn boxes often stop a few pixels short of closing; bridge small gaps.
    outline = ink | ndimage.binary_closing(ink, structure=np.ones((g, g)))
    # A red tick hides the outline where it crosses it. Count red as outline only in those
    # gaps (where closing the ink alone would fill in), so the rest of the tick, which may
    # run close along an edge, doesn't eat into the box.
    k = int(10 * scale) | 1
    outline |= red & ndimage.binary_closing(ink, structure=np.ones((k, k)))
    holes = ndimage.binary_fill_holes(outline) & ~outline
    lab, _ = ndimage.label(holes)
    found = []
    for i, sl in enumerate(ndimage.find_objects(lab), start=1):
        ys, xs = sl
        h, w = ys.stop - ys.start, xs.stop - xs.start
        if not (18 * scale <= w <= 130 * scale and 18 * scale <= h <= 130 * scale):
            continue
        if not 0.45 <= w / h <= 2.2:
            continue
        # Judge the shape by the blue outline alone: red inside the box's own bounds goes back
        # to its interior. Otherwise a tick that runs along an edge dents the empty region and
        # a real box fails the straight-sides test.
        region = ndimage.binary_fill_holes((lab[sl] == i) | red[sl])
        if region.mean() < 0.6 or sorted(_corner_gaps(region))[1] > 0.08 or _edge_bend(region) > 0.022:
            continue
        found.append((ys.start, xs.start, ys.stop, xs.stop))

    if not found:
        return []
    # Boxes sit in one column at the start of each line: keep those near the median left edge.
    med_x = float(np.median([f[1] for f in found]))
    med_w = float(np.median([f[3] - f[1] for f in found]))
    found = sorted(f for f in found if abs(f[1] - med_x) <= 1.5 * med_w)

    boxes = []
    for n, (y0, x0, y1, x1) in enumerate(found, start=1):
        red_px = int(red[y0:y1, x0:x1].sum())
        boxes.append(Checkbox(n, x0, y0, x1, y1, red_px > 0.01 * (y1 - y0) * (x1 - x0)))
    return boxes
