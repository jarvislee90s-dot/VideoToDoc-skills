from __future__ import annotations

from typing import TypedDict

from .mindmap import _MindmapNode


class LayoutConfig:
    def __init__(
        self,
        max_col_height: int = 520,
        chapter_w: int = 130,
        leaf_w: int = 145,
        chapter_h: int = 38,
        leaf_h: int = 26,
        leaf_gap: int = 12,
        chapter_gap: int = 40,
        col_gap: int = 60,
        root_w: int = 115,
        root_h: int = 48,
        top_padding: int = 90,
        margin_x: int = 40,
        margin_y: int = 40,
    ) -> None:
        self.max_col_height = max_col_height
        self.chapter_w = chapter_w
        self.leaf_w = leaf_w
        self.chapter_h = chapter_h
        self.leaf_h = leaf_h
        self.leaf_gap = leaf_gap
        self.chapter_gap = chapter_gap
        self.col_gap = col_gap
        self.root_w = root_w
        self.root_h = root_h
        self.top_padding = top_padding
        self.margin_x = margin_x
        self.margin_y = margin_y


class LayoutNode(TypedDict):
    text: str
    level: int
    x: float
    y: float
    width: float
    height: float
    children: list[LayoutNode]


class MindmapLayout:
    def __init__(
        self,
        root: LayoutNode,
        image_width: float,
        image_height: float,
        column_count: int,
    ) -> None:
        self.root_node = root
        self.image_width = image_width
        self.image_height = image_height
        self._column_count = column_count

    @property
    def column_count(self) -> int:
        return self._column_count

    @property
    def chapter_nodes(self) -> list[LayoutNode]:
        return self.root_node["children"]


def _subtree_height(node: _MindmapNode, cfg: LayoutConfig) -> float:
    if not node.children:
        return cfg.leaf_h
    return sum(_subtree_height(c, cfg) for c in node.children) + (len(node.children) - 1) * cfg.leaf_gap


def _split_columns(root: _MindmapNode, cfg: LayoutConfig) -> list[list[_MindmapNode]]:
    columns: list[list[_MindmapNode]] = []
    current: list[_MindmapNode] = []
    current_h = 0.0
    for ch in root.children:
        h = _subtree_height(ch, cfg) + (cfg.chapter_gap if current else 0)
        if current and current_h + h > cfg.max_col_height:
            columns.append(current)
            current = [ch]
            current_h = _subtree_height(ch, cfg)
        else:
            current.append(ch)
            current_h += _subtree_height(ch, cfg) + (cfg.chapter_gap if len(current) > 1 else 0)
    if current:
        columns.append(current)
    return columns


def _build_layout_node(node: _MindmapNode, cfg: LayoutConfig, x: float, y: float) -> LayoutNode:
    if not node.children:
        return LayoutNode(
            text=node.text,
            level=node.level,
            x=x,
            y=y,
            width=cfg.leaf_w,
            height=cfg.leaf_h,
            children=[],
        )
    children_layout: list[LayoutNode] = []
    child_x = x + (cfg.chapter_w if node.level == 0 else cfg.leaf_w + 70)
    # children stack vertically
    total_h = sum(_subtree_height(c, cfg) for c in node.children) + (len(node.children) - 1) * cfg.leaf_gap
    child_y = y - total_h / 2
    for child in node.children:
        ch = _build_layout_node(child, cfg, child_x, child_y + _subtree_height(child, cfg) / 2)
        children_layout.append(ch)
        child_y += _subtree_height(child, cfg) + cfg.leaf_gap
    return LayoutNode(
        text=node.text,
        level=node.level,
        x=x,
        y=y,
        width=cfg.chapter_w if node.level == 0 else cfg.leaf_w,
        height=cfg.chapter_h if node.level == 0 else cfg.leaf_h,
        children=children_layout,
    )


def compute_layout(root: _MindmapNode, cfg: LayoutConfig | None = None) -> MindmapLayout:
    cfg = cfg or LayoutConfig()
    columns = _split_columns(root, cfg)
    multi_column = len(columns) > 1

    col_layouts: list[LayoutNode] = []
    x = cfg.margin_x + (cfg.root_w + 60 if not multi_column else 0)
    max_col_h = 0.0

    for col_nodes in columns:
        col_h = sum(_subtree_height(n, cfg) for n in col_nodes) + (len(col_nodes) - 1) * cfg.chapter_gap
        y = cfg.top_padding if multi_column else cfg.margin_y + cfg.root_h / 2
        chapter_layouts: list[LayoutNode] = []
        for node in col_nodes:
            chapter = _build_layout_node(node, cfg, x, y + _subtree_height(node, cfg) / 2)
            chapter_layouts.append(chapter)
            y += _subtree_height(node, cfg) + cfg.chapter_gap
        # Wrap column under a synthetic spine node for rendering
        col_layouts.extend(chapter_layouts)
        x += cfg.chapter_w + 115 + cfg.leaf_w + cfg.col_gap
        max_col_h = max(max_col_h, col_h)

    image_width = x + cfg.margin_x
    image_height = (cfg.top_padding + max_col_h + cfg.margin_y) if multi_column else (cfg.margin_y * 2 + cfg.root_h + max_col_h)

    root_x = image_width / 2 if multi_column else cfg.margin_x + cfg.root_w / 2
    root_y = cfg.margin_y if multi_column else image_height / 2

    root_layout = LayoutNode(
        text=root.text,
        level=0,
        x=root_x,
        y=root_y,
        width=cfg.root_w,
        height=cfg.root_h,
        children=col_layouts,
    )

    return MindmapLayout(root_layout, image_width, image_height, len(columns))
