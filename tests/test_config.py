import os
import tempfile
import unittest
from pathlib import Path

from goodnotes_ocr.config import load_env_file


class ConfigTests(unittest.TestCase):
    def test_load_env_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / ".env"
            path.write_text(
                "\n".join(
                    [
                        "FOO=bar",
                        "QUOTED='hello world'",
                        "export EXPORTED=yes",
                    ]
                ),
                encoding="utf-8",
            )
            old_values = {key: os.environ.get(key) for key in ("FOO", "QUOTED", "EXPORTED")}
            try:
                for key in old_values:
                    os.environ.pop(key, None)
                load_env_file(path)
                self.assertEqual(os.environ["FOO"], "bar")
                self.assertEqual(os.environ["QUOTED"], "hello world")
                self.assertEqual(os.environ["EXPORTED"], "yes")
            finally:
                for key, value in old_values.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
