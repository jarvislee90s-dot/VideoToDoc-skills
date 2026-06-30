from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from PIL import Image

from videotodoc.mindmap import render_mindmap_and_refresh_docs


def _fake_mmdc_runner(args: list[str]) -> None:
    output_path = Path(args[args.index("-o") + 1])
    img = Image.new("RGBA", (100, 100), (255, 255, 255, 0))
    img.save(output_path)


def test_render_uses_tidy_tree_config(tmp_path: Path):
    mmd = tmp_path / "mindmap.mmd"
    mmd.write_text("mindmap\n  root((R))\n    A\n      a1\n", encoding="utf-8")

    captured: list[str] = []

    def fake_run_mmdc(args: list[str]) -> None:
        input_path = Path(args[args.index("-i") + 1])
        output_path = Path(args[args.index("-o") + 1])
        captured.append(input_path.read_text(encoding="utf-8"))
        img = Image.new("RGBA", (100, 100), (255, 255, 255, 0))
        img.save(output_path)

    with patch("videotodoc.mindmap._run_mmdc", side_effect=fake_run_mmdc):
        image_paths, _ = render_mindmap_and_refresh_docs(tmp_path)

    assert len(image_paths) == 1
    assert "layout: tidy-tree" in captured[0]
    assert "1. A" in captured[0]


def test_render_splits_large_mindmap(tmp_path: Path):
    lines = ["mindmap", "  root((R))"]
    for i in range(30):
        lines.append(f"    Ch{i}")
        for j in range(3):
            lines.append(f"      leaf{i}_{j}")
    mmd = tmp_path / "mindmap.mmd"
    mmd.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with patch("videotodoc.mindmap._run_mmdc", side_effect=_fake_mmdc_runner):
        image_paths, _ = render_mindmap_and_refresh_docs(tmp_path)

    assert len(image_paths) >= 2


def test_render_refreshes_markdown_and_docx(tmp_path: Path):
    mmd = tmp_path / "mindmap.mmd"
    mmd.write_text("mindmap\n  root((R))\n    A\n      a1\n", encoding="utf-8")
    md = tmp_path / "讲义.md"
    md.write_text("# 标题\n\n## 图文讲义\n", encoding="utf-8")
    docx = tmp_path / "讲义.docx"
    docx.write_bytes(b"fake docx")

    with patch("videotodoc.mindmap._run_mmdc", side_effect=_fake_mmdc_runner), \
         patch("videotodoc.mindmap.markdown_to_docx") as mock_docx:
        mock_docx.return_value = docx
        image_paths, refreshed = render_mindmap_and_refresh_docs(tmp_path)

    assert len(image_paths) == 1
    content = md.read_text(encoding="utf-8")
    assert "## 思维导图" in content
    assert "![思维导图]" in content
    assert len(refreshed) == 1
