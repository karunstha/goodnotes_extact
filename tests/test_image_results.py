import unittest
from pathlib import Path

from goodnotes_ocr.image_results import image_batch_to_dicts
from goodnotes_ocr.models import PageImage, PageImageBatch


class ImageResultsTests(unittest.TestCase):
    def test_image_batch_to_dicts(self):
        batch = PageImageBatch(
            source_url="https://example.com",
            page_count=10,
            images=(PageImage(page=3, image_path=Path("output/page-3.png")),),
        )
        self.assertEqual(
            image_batch_to_dicts(batch),
            [
                {
                    "source_url": "https://example.com",
                    "page": 3,
                    "page_count": 10,
                    "image_path": "output/page-3.png",
                    "mime_type": "image/png",
                    "used_pdf": False,
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
