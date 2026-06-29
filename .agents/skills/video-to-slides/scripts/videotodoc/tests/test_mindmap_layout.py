from videotodoc.mindmap_layout import LayoutConfig, LayoutNode, compute_layout
from videotodoc.mindmap import _parse_mermaid_tree

LONG_MMD = """mindmap
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


def _collect_leaves(node: LayoutNode) -> list[LayoutNode]:
    if not node["children"]:
        return [node]
    leaves: list[LayoutNode] = []
    for child in node["children"]:
        leaves.extend(_collect_leaves(child))
    return leaves


def test_multi_column_root_on_top():
    root = _parse_mermaid_tree(LONG_MMD)
    cfg = LayoutConfig(max_col_height=200, chapter_h=30, leaf_h=20, leaf_gap=8, chapter_gap=20)
    layout = compute_layout(root, cfg)
    assert layout.column_count >= 2
    # Root is centered at top
    assert layout.root_node["y"] < layout.chapter_nodes[0]["y"]
    assert abs(layout.root_node["x"] - layout.image_width / 2) < 10
    # Chapters below root
    for ch in layout.chapter_nodes:
        assert ch["y"] > layout.root_node["y"]
        assert ch["width"] == cfg.chapter_w
        assert ch["height"] == cfg.chapter_h
    for leaf in _collect_leaves(layout.root_node):
        assert leaf["width"] == cfg.leaf_w
        assert leaf["height"] == cfg.leaf_h
    expected_width = (
        2 * cfg.margin_x
        + layout.column_count * (cfg.chapter_w + 115 + cfg.leaf_w)
        + (layout.column_count - 1) * cfg.col_gap
    )
    assert abs(layout.image_width - expected_width) < 1


def test_single_column_root_on_left():
    mmd = """mindmap
  root((R))
    A
      a1
      a2
    B
      b1
"""
    root = _parse_mermaid_tree(mmd)
    cfg = LayoutConfig(max_col_height=500, chapter_h=30, leaf_h=20, leaf_gap=8, chapter_gap=20)
    layout = compute_layout(root, cfg)
    assert layout.column_count == 1
    # Root is on the left
    assert layout.root_node["x"] < layout.chapter_nodes[0]["x"]
    assert abs(layout.root_node["y"] - layout.image_height / 2) < 10
    # Chapters are to the right of the root
    for ch in layout.chapter_nodes:
        assert ch["x"] > layout.root_node["x"]
        assert ch["width"] == cfg.chapter_w
        assert ch["height"] == cfg.chapter_h
    for leaf in _collect_leaves(layout.root_node):
        assert leaf["width"] == cfg.leaf_w
        assert leaf["height"] == cfg.leaf_h
    expected_width = 2 * cfg.margin_x + cfg.root_w + 60 + cfg.chapter_w + 115 + cfg.leaf_w
    assert abs(layout.image_width - expected_width) < 1
