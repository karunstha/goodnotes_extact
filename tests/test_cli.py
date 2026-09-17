import tempfile
import unittest
from pathlib import Path

from goodnotes_ocr.cli import _load_response_schema


class CliTests(unittest.TestCase):
    def test_load_inline_response_schema(self):
        schema = _load_response_schema('{"type": "object"}')
        self.assertEqual(schema, {"type": "object"})

    def test_load_response_schema_from_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "schema.json"
            path.write_text('{"type": "object"}', encoding="utf-8")
            schema = _load_response_schema(f"@{path}")
        self.assertEqual(schema, {"type": "object"})

    def test_response_schema_must_be_object(self):
        with self.assertRaises(ValueError):
            _load_response_schema("[]")


if __name__ == "__main__":
    unittest.main()
