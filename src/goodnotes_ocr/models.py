from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BrowserOptions:
    headless: bool = True
    timeout_ms: int = 45_000
    settle_ms: int = 1_000
    viewport_width: int = 1500
    viewport_height: int = 1910
    device_scale_factor: float = 2.0
    max_probe_page: int = 2_000


@dataclass(frozen=True)
class PageImage:
    page: int
    image_path: Path


@dataclass(frozen=True)
class PageImageBatch:
    source_url: str
    page_count: int | None
    images: tuple[PageImage, ...]
    used_pdf: bool = False


@dataclass(frozen=True)
class VlmPageResult:
    source_url: str
    page: int
    page_count: int | None
    image_path: Path
    model: str
    result: Any

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_url": self.source_url,
            "page": self.page,
            "page_count": self.page_count,
            "image_path": str(self.image_path),
            "model": self.model,
            "result": self.result,
        }
