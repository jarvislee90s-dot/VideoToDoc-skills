from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import TypedDict

from .mindmap import _MindmapNode


@dataclass
class LayoutConfig:
    max_col_height: int = 520
    chapter_w: int = 130
    leaf_w: int = 145
    chapter_h: int = 38
    leaf_h: int = 26
    leaf_gap: int = 12
    min_leaf_gap: int = 14
    chapter_gap: int = 40
    col_gap: int = 60
    max_columns: int = 4
    root_w: int = 115
    root_h: int = 48
    top_padding: int = 90
    margin_x: int = 40
    margin_y: int = 40
    branch_spacing: int = 115
    leaf_branch_spacing: int = 70
    root_to_chapter_gap: int = 60


class LayoutNode(TypedDict):
    text: str
    level: int
    x: float
    y: float
    width: float
    height: float
    children: list[LayoutNode]
    is_column_entry: bool


class MindmapLayout:
    def __init__(
        self,
        root: LayoutNode,
        image_width: float,
        image_height: float,
        column_count: int,
        beam_y: float | None = None,
        column_entries: list[LayoutNode] | None = None,
    ) -> None:
        self.root_node = root
        self.image_width = image_width
        self.image_height = image_height
        self._column_count = column_count
        self.beam_y = beam_y
        self.column_entries = column_entries or []

    @property
    def column_count(self) -> int:
        return self._column_count

    @property
    def chapter_nodes(self) -> list[LayoutNode]:
        if self._column_count <= 1:
            return self.root_node["children"]
        chapters: list[LayoutNode] = []
        for col in self.root_node["children"]:
            chapters.extend(col["children"])
        return chapters


def _leaf_spacing(cfg: LayoutConfig) -> int:
    return max(cfg.leaf_gap, cfg.min_leaf_gap)


def _subtree_height(node: _MindmapNode, cfg: LayoutConfig) -> float:
    if not node.children:
        return cfg.leaf_h
    return sum(_subtree_height(c, cfg) for c in node.children) + (len(node.children) - 1) * _leaf_spacing(cfg)


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

    if len(columns) > cfg.max_columns:
        merged: list[_MindmapNode] = []
        for col in columns[cfg.max_columns - 1 :]:
            merged.extend(col)
        columns = columns[: cfg.max_columns - 1] + [merged]
    return columns


def _shift_layout_node(node: LayoutNode, dy: float) -> None:
    node["y"] += dy
    for child in node["children"]:
        _shift_layout_node(child, dy)


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
            is_column_entry=False,
        )
    children_layout: list[LayoutNode] = []
    child_x = x + (cfg.chapter_w + cfg.branch_spacing if node.level == 1 else cfg.leaf_w + cfg.leaf_branch_spacing)
    spacing = _leaf_spacing(cfg)
    total_h = sum(_subtree_height(c, cfg) for c in node.children) + (len(node.children) - 1) * spacing
    child_y = y - total_h / 2
    for child in node.children:
        ch = _build_layout_node(child, cfg, child_x, child_y + _subtree_height(child, cfg) / 2)
        children_layout.append(ch)
        child_y += _subtree_height(child, cfg) + spacing
    return LayoutNode(
        text=node.text,
        level=node.level,
        x=x,
        y=y,
        width=cfg.chapter_w if node.level == 1 else cfg.leaf_w,
        height=cfg.chapter_h if node.level == 1 else cfg.leaf_h,
        children=children_layout,
        is_column_entry=False,
    )


def compute_layout(root: _MindmapNode, cfg: LayoutConfig | None = None) -> MindmapLayout:
    cfg = cfg or LayoutConfig()

    if not root.children:
        image_width = 2 * cfg.margin_x + cfg.root_w
        image_height = 2 * cfg.margin_y + cfg.root_h
        root_layout = LayoutNode(
            text=root.text,
            level=0,
            x=cfg.margin_x + cfg.root_w / 2,
            y=image_height / 2,
            width=cfg.root_w,
            height=cfg.root_h,
            children=[],
            is_column_entry=False,
        )
        return MindmapLayout(root_layout, image_width, image_height, 1)

    columns = _split_columns(root, cfg)
    multi_column = len(columns) > 1

    col_chapter_layouts: list[list[LayoutNode]] = []
    x = cfg.margin_x + (cfg.root_w + cfg.root_to_chapter_gap if not multi_column else 0)
    max_col_h = 0.0
    col_centers: list[float] = []

    for i, col_nodes in enumerate(columns):
        col_centers.append(x + cfg.chapter_w / 2)
        col_h = sum(_subtree_height(n, cfg) for n in col_nodes) + (len(col_nodes) - 1) * cfg.chapter_gap
        y = cfg.top_padding if multi_column else cfg.margin_y + cfg.root_h / 2
        chapter_layouts: list[LayoutNode] = []
        for node in col_nodes:
            chapter = _build_layout_node(node, cfg, x, y + _subtree_height(node, cfg) / 2)
            chapter_layouts.append(chapter)
            y += _subtree_height(node, cfg) + cfg.chapter_gap
        col_chapter_layouts.append(chapter_layouts)
        x += cfg.chapter_w + cfg.branch_spacing + cfg.leaf_w
        if i < len(columns) - 1:
            x += cfg.col_gap
        max_col_h = max(max_col_h, col_h)

    image_width = x + cfg.margin_x
    if multi_column:
        image_height = cfg.top_padding + max_col_h + cfg.margin_y
    else:
        image_height = cfg.margin_y * 2 + cfg.root_h + max_col_h

    if multi_column:
        min_chapter_top = min(ch["y"] - ch["height"] / 2 for col in col_chapter_layouts for ch in col)
        beam_gap = 15
        drop_length = 25
        beam_y = min_chapter_top - beam_gap
        root_y = beam_y - drop_length - cfg.root_h / 2
        if root_y < cfg.margin_y + cfg.root_h / 2:
            delta = cfg.margin_y + cfg.root_h / 2 - root_y
            root_y += delta
            beam_y += delta
            for col in col_chapter_layouts:
                for ch in col:
                    _shift_layout_node(ch, delta)
            image_height += delta
        root_x = image_width / 2

        column_entries: list[LayoutNode] = []
        children: list[LayoutNode] = []
        for col_center, col_chapters in zip(col_centers, col_chapter_layouts):
            entry = LayoutNode(
                text="",
                level=1,
                x=col_center,
                y=beam_y,
                width=0,
                height=0,
                children=col_chapters,
                is_column_entry=True,
            )
            column_entries.append(entry)
            children.append(entry)

        root_layout = LayoutNode(
            text=root.text,
            level=0,
            x=root_x,
            y=root_y,
            width=cfg.root_w,
            height=cfg.root_h,
            children=children,
            is_column_entry=False,
        )
    else:
        root_x = cfg.margin_x + cfg.root_w / 2
        root_y = image_height / 2
        column_entries = []
        beam_y = None
        root_layout = LayoutNode(
            text=root.text,
            level=0,
            x=root_x,
            y=root_y,
            width=cfg.root_w,
            height=cfg.root_h,
            children=[ch for col in col_chapter_layouts for ch in col],
            is_column_entry=False,
        )

    if image_width > 3000:
        warnings.warn(
            f"思维导图整体宽度 {image_width:.0f}px 超过 3000px，建议精简节点。",
            stacklevel=2,
        )

    return MindmapLayout(
        root_layout,
        image_width,
        image_height,
        len(columns),
        beam_y=beam_y,
        column_entries=column_entries,
    )
