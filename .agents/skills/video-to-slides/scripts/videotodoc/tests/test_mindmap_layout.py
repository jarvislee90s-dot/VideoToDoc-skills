from videotodoc.mindmap_layout import LayoutConfig, compute_layout
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
