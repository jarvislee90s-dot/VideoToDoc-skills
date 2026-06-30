import tempfile
from pathlib import Path

from videotodoc.document import ensure_mindmap_link


def test_ensure_mindmap_link_accepts_multiple_images():
    with tempfile.TemporaryDirectory() as tmp:
        md = Path(tmp) / "test.md"
        md.write_text("# Title\n\n## 图文讲义\n", encoding="utf-8")
        img1 = Path(tmp) / "mindmap_01.png"
        img2 = Path(tmp) / "mindmap_02.png"
        img1.write_text("", encoding="utf-8")
        img2.write_text("", encoding="utf-8")
        ensure_mindmap_link(md, [img1, img2])
        text = md.read_text(encoding="utf-8")
        assert "![思维导图](mindmap_01.png)" in text
        assert "![思维导图](mindmap_02.png)" in text


def test_ensure_mindmap_link_replaces_existing_single_image():
    with tempfile.TemporaryDirectory() as tmp:
        md = Path(tmp) / "test.md"
        md.write_text("# Title\n\n## 思维导图\n\n![思维导图](old.png)\n", encoding="utf-8")
        img = Path(tmp) / "new.png"
        img.write_text("", encoding="utf-8")
        ensure_mindmap_link(md, img)
        text = md.read_text(encoding="utf-8")
        assert "![思维导图](new.png)" in text
        assert "old.png" not in text


def test_ensure_mindmap_link_replaces_existing_multiple_images():
    with tempfile.TemporaryDirectory() as tmp:
        md = Path(tmp) / "test.md"
        md.write_text("# Title\n\n## 思维导图\n\n![思维导图](old_01.png)\n\n![思维导图](old_02.png)\n", encoding="utf-8")
        img1 = Path(tmp) / "new_01.png"
        img2 = Path(tmp) / "new_02.png"
        img1.write_text("", encoding="utf-8")
        img2.write_text("", encoding="utf-8")
        ensure_mindmap_link(md, [img1, img2])
        text = md.read_text(encoding="utf-8")
        assert "![思维导图](new_01.png)" in text
        assert "![思维导图](new_02.png)" in text
        assert "old_01.png" not in text
        assert "old_02.png" not in text


def test_generate_mindmap_adds_chapter_numbers(tmp_path: Path):
    from videotodoc.document import generate_mindmap
    from videotodoc.models import Section

    sections = [
        Section(slide_index=1, image_path="", start_ms=0, end_ms=1000, capture_ms=500, transcript="第一页内容", segment_indexes=[0]),
        Section(slide_index=2, image_path="", start_ms=1000, end_ms=2000, capture_ms=1500, transcript="第二页内容", segment_indexes=[1]),
    ]
    out = tmp_path / "mindmap.mmd"
    generate_mindmap("测试", sections, out)
    text = out.read_text(encoding="utf-8")
    assert "1. 第 1 页" in text
    assert "2. 第 2 页" in text


def test_generate_mindmap_keeps_root_syntax_valid(tmp_path: Path):
    from videotodoc.document import generate_mindmap
    from videotodoc.models import Section

    sections = [Section(slide_index=1, image_path="", start_ms=0, end_ms=1000, capture_ms=500, transcript="内容", segment_indexes=[0])]
    out = tmp_path / "mindmap.mmd"
    generate_mindmap("Git(Hub): 核心概念", sections, out)
    text = out.read_text(encoding="utf-8")
    assert "root((" in text
    assert "root（（" not in text
