import warnings
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from PIL import Image

from videotodoc.mindmap import (
    _parse_mermaid_tree,
    _render_mindmap_with_python_from_tree,
    _wrap_text,
)
from videotodoc.mindmap_layout import LayoutConfig, LayoutNode, compute_layout


def _collect_nodes(node: LayoutNode) -> list[LayoutNode]:
    nodes = [node]
    for child in node["children"]:
        nodes.extend(_collect_nodes(child))
    return nodes


def _boxes_overlap(a: LayoutNode, b: LayoutNode) -> bool:
    if a.get("is_column_entry") or b.get("is_column_entry"):
        return False
    ax1, ay1 = a["x"] - 2, a["y"] - 2
    ax2, ay2 = a["x"] + a["width"] + 2, a["y"] + a["height"] + 2
    bx1, by1 = b["x"] - 2, b["y"] - 2
    bx2, by2 = b["x"] + b["width"] + 2, b["y"] + b["height"] + 2
    return ax1 < bx2 and ax2 > bx1 and ay1 < by2 and ay2 > by1


def test_only_root_node():
    mmd = "mindmap\n  root((R))\n"
    root = _parse_mermaid_tree(mmd)
    cfg = LayoutConfig()
    layout = compute_layout(root, cfg)
    assert layout.column_count == 1
    assert layout.root_node["children"] == []
    assert layout.image_width == 2 * cfg.margin_x + cfg.root_w
    assert layout.image_height == 2 * cfg.margin_y + cfg.root_h
    assert layout.root_node["x"] == cfg.margin_x + cfg.root_w / 2
    assert layout.root_node["y"] == layout.image_height / 2


def test_deep_levels_rendered():
    mmd = """mindmap
  root((R))
    A
      a1
        a11
          a111
"""
    root = _parse_mermaid_tree(mmd)
    cfg = LayoutConfig()
    layout = compute_layout(root, cfg)
    nodes = _collect_nodes(layout.root_node)
    levels = {node["level"] for node in nodes}
    assert max(levels) >= 3
    deep = [n for n in nodes if n["level"] >= 3 and not n.get("is_column_entry")]
    assert deep
    for node in deep:
        assert node["width"] == cfg.leaf_w
        assert node["height"] == cfg.leaf_h


def test_long_text_wrap_and_truncate():
    # 宽度 10，最多 20 字符，超过截断
    assert _wrap_text("short", 10) == "short"
    wrapped = _wrap_text("0123456789abcdefghij", 10)
    assert wrapped == "0123456789\nabcdefghij"
    truncated = _wrap_text("0123456789abcdefghijklmnop", 10)
    assert "\n" in truncated
    assert truncated.endswith("…")
    assert len(truncated.replace("\n", "").replace("…", "x")) <= 20


def test_min_leaf_gap_enforced():
    mmd = """mindmap
  root((R))
    A
      a1
      a2
"""
    root = _parse_mermaid_tree(mmd)
    cfg = LayoutConfig(leaf_gap=8, min_leaf_gap=14)
    layout = compute_layout(root, cfg)
    chapter = layout.chapter_nodes[0]
    leaves = chapter["children"]
    assert len(leaves) == 2
    center_distance = abs(leaves[0]["y"] - leaves[1]["y"])
    gap = center_distance - cfg.leaf_h
    assert gap >= cfg.min_leaf_gap


def test_max_columns_limit():
    # 5 个章节，每个高度超过单栏，强制分栏后应被限制为 4 栏
    lines = ["mindmap", "  root((R))"]
    for i in range(5):
        lines.append(f"    C{i}")
        for j in range(20):
            lines.append(f"      c{i}_{j}")
    mmd = "\n".join(lines)
    root = _parse_mermaid_tree(mmd)
    cfg = LayoutConfig(max_columns=4)
    layout = compute_layout(root, cfg)
    assert layout.column_count <= cfg.max_columns


def test_super_wide_emits_warning():
    lines = ["mindmap", "  root((R))"]
    for i in range(4):
        lines.append(f"    C{i}")
        for j in range(20):
            lines.append(f"      c{i}_{j}")
    mmd = "\n".join(lines)
    root = _parse_mermaid_tree(mmd)
    cfg = LayoutConfig(
        chapter_w=300,
        leaf_w=400,
        branch_spacing=300,
        max_columns=4,
    )
    with pytest.warns(UserWarning, match="超过 3000px"):
        layout = compute_layout(root, cfg)
    assert layout.image_width > 3000


def test_multi_column_has_beam_and_entries():
    mmd = """mindmap
  root((R))
    A
      a1
      a2
      a3
      a4
    B
      b1
      b2
      b3
      b4
    C
      c1
      c2
      c3
      c4
    D
      d1
      d2
      d3
      d4
"""
    root = _parse_mermaid_tree(mmd)
    cfg = LayoutConfig(max_col_height=200, chapter_h=30, leaf_h=20, leaf_gap=8, chapter_gap=20)
    layout = compute_layout(root, cfg)
    assert layout.column_count >= 2
    assert layout.beam_y is not None
    assert len(layout.column_entries) == layout.column_count
    # 根节点在横梁上方
    assert layout.root_node["y"] + layout.root_node["height"] / 2 < layout.beam_y
    # 栏入口在横梁上
    for entry in layout.column_entries:
        assert entry["y"] == layout.beam_y
        assert entry.get("is_column_entry")


def test_rendered_nodes_do_not_overlap():
    mmd = """mindmap
  root((R))
    A
      a1
      a2
      a3
    B
      b1
      b2
    C
      c1
      c2
      c3
      c4
"""
    root = _parse_mermaid_tree(mmd)
    cfg = LayoutConfig(max_col_height=200)
    layout = compute_layout(root, cfg)
    nodes = [n for n in _collect_nodes(layout.root_node) if not n.get("is_column_entry")]
    for i, a in enumerate(nodes):
        for b in nodes[i + 1 :]:
            assert not _boxes_overlap(a, b)


def test_render_creates_non_empty_png_for_complex_tree():
    mmd = """mindmap
  root((R))
    A
      a1
      a2
    B
      b1
      b2
      b3
"""
    root = _parse_mermaid_tree(mmd)
    with TemporaryDirectory() as tmp:
        out = Path(tmp) / "mindmap.png"
        _render_mindmap_with_python_from_tree(root, out)
        img = Image.open(out)
        assert img.format == "PNG"
        assert img.width >= 200
        assert img.height >= 100
