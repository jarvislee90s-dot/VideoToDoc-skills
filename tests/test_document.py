from pathlib import Path
import importlib.util
import tempfile
import unittest

from videotodoc.document import generate_mindmap, markdown_to_docx, render_compact_markdown, render_original_markdown
from videotodoc.config import Settings
from videotodoc.models import Section


class DocumentTests(unittest.TestCase):
    def test_generate_mindmap_and_markdown_variants(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sections = [
                Section(1, "slides/0001.png", 0, 1000, 900, "这是第一页内容，\n\n包含 API。", [0]),
                Section(2, "slides/0002.png", 1000, 2000, 1900, "本页无讲解。", [], ["empty_transcript_match"]),
            ]

            mindmap = generate_mindmap("测试课程", sections, tmp_path / "mindmap.mmd", Settings(mindmap_backend="rule"))
            raw_path = render_original_markdown("测试课程", sections, tmp_path / "draft.md")
            compact_path = render_compact_markdown("测试课程", sections, tmp_path / "draft_compact.md", tmp_path / "mindmap.png")

            self.assertIn("mindmap", mindmap)
            raw = raw_path.read_text(encoding="utf-8")
            compact = compact_path.read_text(encoding="utf-8")
            self.assertIn("这是第一页内容，\n\n包含 API。", raw)
            self.assertIn("### 第 1 页 · 00:00 - 00:01", compact)
            self.assertIn("这是第一页内容，包含 API。", compact)
            self.assertIn("![思维导图](mindmap.png)", compact)

    @unittest.skipIf(importlib.util.find_spec("docx") is None, "python-docx is not installed")
    def test_markdown_to_docx_uses_fixed_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            markdown_path = tmp_path / "draft_compact.md"
            markdown_path.write_text(
                "# 测试课程\n\n"
                "## 图文讲义\n\n"
                "### 第 1 页 · 00:00 - 00:01\n\n"
                "第一段内容。\n\n"
                "---\n\n"
                "### 第 2 页 · 00:01 - 00:02\n\n"
                "第二段内容。\n",
                encoding="utf-8",
            )
            docx_path = markdown_to_docx(markdown_path, tmp_path / "draft.docx")

            self.assertIsNotNone(docx_path)
            self.assertTrue((tmp_path / "draft.docx").exists())


if __name__ == "__main__":
    unittest.main()
