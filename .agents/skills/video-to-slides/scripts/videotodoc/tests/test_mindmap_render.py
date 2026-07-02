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


def test_render_keeps_single_image_for_large_mindmap(tmp_path: Path):
    lines = ["mindmap", "  root((R))"]
    for i in range(30):
        lines.append(f"    Ch{i}")
        for j in range(3):
            lines.append(f"      leaf{i}_{j}")
    mmd = tmp_path / "mindmap.mmd"
    mmd.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with patch("videotodoc.mindmap._run_mmdc", side_effect=_fake_mmdc_runner):
        image_paths, _ = render_mindmap_and_refresh_docs(tmp_path)

    assert len(image_paths) == 1


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


def test_render_generates_missing_docx_for_compact_and_semantic(tmp_path: Path):
    from videotodoc.mindmap import render_mindmap_and_refresh_docs

    mmd = tmp_path / "mindmap.mmd"
    mmd.write_text("mindmap\n  root((R))\n    A\n      a1\n", encoding="utf-8")

    compact_md = tmp_path / "视频_讲义_紧凑版_20260101_120000.md"
    compact_md.write_text("# 紧凑\n\n## 图文讲义\n", encoding="utf-8")
    semantic_md = tmp_path / "视频_讲义_整理版_20260101_120000.md"
    semantic_md.write_text("# 整理\n\n## 图文讲义\n", encoding="utf-8")
    original_md = tmp_path / "视频_讲义_20260101_120000.md"
    original_md.write_text("# 原始\n", encoding="utf-8")

    generated_docxes: list[Path] = []

    def fake_markdown_to_docx(md_path: Path, docx_path: Path) -> Path:
        docx_path.write_bytes(b"fake docx")
        generated_docxes.append(docx_path)
        return docx_path

    with patch("videotodoc.mindmap._run_mmdc", side_effect=_fake_mmdc_runner), \
         patch("videotodoc.mindmap.markdown_to_docx", side_effect=fake_markdown_to_docx):
        image_paths, refreshed = render_mindmap_and_refresh_docs(tmp_path)

    assert len(image_paths) == 1
    assert len(refreshed) == 2
    assert any("视频_讲义_20260101_120000.docx" == p.name for p in refreshed)
    assert any("视频_讲义_整理版_20260101_120000.docx" == p.name for p in refreshed)
    assert not any("视频_讲义_紧凑版_" in p.name for p in refreshed)
