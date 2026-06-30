from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from PIL import Image

from videotodoc.mindmap import render_mindmap_and_refresh_docs
from videotodoc.mindmap_mermaid import split_mmd_by_chapters
from videotodoc.utils import VideoToDocError


def test_split_avoids_sparse_last_image():
    from videotodoc.mindmap_mermaid import add_chapter_numbers

    text = """mindmap
  root((R))
    A
      a1
      a2
      a3
      a4
      a5
    B
      b1
"""
    numbered = add_chapter_numbers(text)
    parts = split_mmd_by_chapters(numbered, max_nodes=10, min_chapters=1, min_nodes=3)
    assert len(parts) == 1
    assert "1. A" in parts[0]
    assert "2. B" in parts[0]


def test_render_raises_on_oversized_png(tmp_path: Path):
    mmd = tmp_path / "mindmap.mmd"
    mmd.write_text("mindmap\n  root((R))\n    A\n", encoding="utf-8")

    def fake_run_mmdc(args: list[str]) -> None:
        output_path = Path(args[args.index("-o") + 1])
        img = Image.new("RGBA", (4000, 100), (255, 255, 255, 0))
        img.save(output_path)

    with patch("videotodoc.mindmap._run_mmdc", side_effect=fake_run_mmdc):
        try:
            render_mindmap_and_refresh_docs(tmp_path)
            assert False, "应该抛出尺寸超限错误"
        except VideoToDocError as exc:
            assert "尺寸过大" in str(exc)
