from pathlib import Path
import tempfile
import unittest

from videotodoc.config import load_config
from videotodoc.config import Settings


class ConfigTests(unittest.TestCase):
    def test_load_simple_yaml(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            config = tmp_path / "config.yaml"
            config.write_text("asr_backend: mock\nscene_threshold: 0.3\nterms:\n  api: API\n", encoding="utf-8")

            settings = load_config(config)

            self.assertEqual(settings.asr_backend, "mock")
            self.assertEqual(settings.scene_threshold, 0.3)
            self.assertEqual(settings.terms["api"], "API")

    def test_defaults_prefer_mlx_whisper(self):
        settings = Settings()

        self.assertEqual(settings.asr_backend, "mlx-whisper")
        self.assertIn("mlx-community", settings.asr_model)


if __name__ == "__main__":
    unittest.main()
