from __future__ import annotations

from typing import Any

from goodnotes_ocr.models import PageImageBatch


def image_batch_to_dicts(batch: PageImageBatch) -> list[dict[str, Any]]:
    return [
        {
            "source_url": batch.source_url,
            "page": image.page,
            "page_count": batch.page_count,
            "image_path": str(image.image_path),
            "mime_type": "image/png",
            "used_pdf": batch.used_pdf,
        }
        for image in batch.images
    ]
