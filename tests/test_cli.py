import os
import tempfile
import unittest
from pathlib import Path

from videotodoc.cli import _find_sections_path


class CliTests(unittest.TestCase):
    def test_find_sections_path_prefers_latest_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp) / "cache"
            cache_dir.mkdir()
            old_path = cache_dir / "zzz.sections.json"
            new_path = cache_dir / "aaa.sections.json"
            old_path.write_text("{}", encoding="utf-8")
            new_path.write_text("{}", encoding="utf-8")
            os.utime(old_path, ns=(1_000, 1_000))
            os.utime(new_path, ns=(2_000, 2_000))

            self.assertEqual(_find_sections_path(Path(tmp)), new_path)


if __name__ == "__main__":
    unittest.main()
