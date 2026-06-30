from __future__ import annotations

from videotodoc.mindmap_mermaid import (
    add_chapter_numbers,
    count_nodes,
    inject_tidy_tree_config,
    split_mmd_by_chapters,
)


def test_inject_tidy_tree_config():
    text = "mindmap\n  root((R))\n    A\n"
    result = inject_tidy_tree_config(text)
    assert result.startswith("---\nconfig:\n  layout: tidy-tree\n---\n\n")
    assert "mindmap\n  root((R))\n    A\n" in result


def test_add_chapter_numbers():
    text = """mindmap
  root((R))
    A
      a1
    B
      b1
"""
    result = add_chapter_numbers(text)
    assert "1. A" in result
    assert "2. B" in result
    assert "    a1" in result  # 子节点不加序号


def test_split_mmd_by_chapters():
    text = """mindmap
  root((R))
    A
      a1
      a2
    B
      b1
    C
      c1
"""
    numbered = add_chapter_numbers(text)
    parts = split_mmd_by_chapters(numbered, max_nodes=5, min_chapters=2, min_nodes=1)
    assert len(parts) == 2
    assert "1. A" in parts[0] and "2. B" in parts[0]
    assert "3. C" in parts[1]


def test_count_nodes():
    text = """mindmap
  root((R))
    A
      a1
      a2
    B
      b1
"""
    assert count_nodes(text) == 6
