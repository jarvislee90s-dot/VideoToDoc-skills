"""紧凑版/整理版多图展示测试（任务 9）。"""

from pathlib import Path


def test_compact_markdown_multi_image_in_time_order(tmp_path: Path) -> None:
    from videotodoc.document import render_compact_markdown
    from videotodoc.models import Section

    sections = [
        Section(
            slide_index=6,
            image_path="p06_02_main_185.8s.png",
            image_paths=[
                "p06_01_150.0s_cand.png",
                "p06_02_main_185.8s.png",
                "p06_03_210.0s_cand.png",
            ],
            start_ms=138600, end_ms=213900, capture_ms=213400,
            transcript="推导 LLM",
            segment_indexes=[6],
        ),
    ]
    out = tmp_path / "compact.md"
    render_compact_markdown("测试", sections, out)
    text = out.read_text(encoding="utf-8")
    # 验证 markdown 顺序：cand → main → cand（按时间，主图在中间）
    cand1_pos = text.find("p06_01_150.0s_cand")
    main_pos = text.find("p06_02_main_185.8s")
    cand3_pos = text.find("p06_03_210.0s_cand")
    assert cand1_pos < main_pos < cand3_pos


def test_semantic_markdown_multi_image_placeholders(tmp_path: Path) -> None:
    from videotodoc.document import ensure_semantic_markdown
    from videotodoc.models import Section

    sections = [
        Section(
            slide_index=6,
            image_path="p06_02_main_185.8s.png",
            image_paths=[
                "p06_01_150.0s_cand.png",
                "p06_02_main_185.8s.png",
                "p06_03_210.0s_cand.png",
            ],
            start_ms=138600, end_ms=213900, capture_ms=213400,
            transcript="推导 LLM",
            segment_indexes=[6],
        ),
    ]
    out = tmp_path / "semantic.md"
    ensure_semantic_markdown("测试", sections, out)
    text = out.read_text(encoding="utf-8")
    # 验证占位符顺序：IMAGE:6-1 → IMAGE:6-2:main → IMAGE:6-3
    img1 = text.find("<!-- IMAGE:6-1 -->")
    img2 = text.find("<!-- IMAGE:6-2:main -->")
    img3 = text.find("<!-- IMAGE:6-3 -->")
    assert img1 < img2 < img3


def test_compact_markdown_single_image_no_change(tmp_path: Path) -> None:
    """keep_all=False（单图）保持原有展示方式。"""
    from videotodoc.document import render_compact_markdown
    from videotodoc.models import Section

    sections = [
        Section(
            slide_index=1,
            image_path="p01_01_main_31.8s.png",
            image_paths=["p01_01_main_31.8s.png"],  # 单图
            start_ms=0, end_ms=32280, capture_ms=31780,
            transcript="开场",
            segment_indexes=[0],
        ),
    ]
    out = tmp_path / "compact.md"
    render_compact_markdown("测试", sections, out)
    text = out.read_text(encoding="utf-8")
    # 单图时 image_path 与 image_paths 第一个一致
    assert "p01_01_main_31.8s.png" in text
