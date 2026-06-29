# 思维导图渲染形态重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `video-to-slides` 的思维导图从 Mermaid 圆形散射改为目录树状布局，支持多栏自适应根节点位置，并默认使用 Python 渲染器。

**Architecture:** 复用并扩展 `videotodoc/mindmap.py` 中的 Python fallback。新增多栏布局引擎，按章节顺序和子树高度自动分栏；单栏时根节点在左，多栏时根节点置顶。节点使用带框 + 层级配色渲染，最终输出单张 PNG。

**Tech Stack:** Python 3.11+, Pillow, pytest

## Global Constraints

- 默认输出仍是一张 PNG，不引入前端/浏览器依赖。
- 保留 Mermaid `.mmd` 源文件生成，但默认不再用 `mmdc` 渲染。
- 节点层级不超过 3 级；Agent 生成的 `.mmd` 负责控制层级深度。
- 最终产物名保持 `<视频标题>_思维导图_<时间戳>.png`。
- 不新增除 Pillow 外的第三方依赖。

---

### Task 1: 为 `.mmd` 解析器补充单元测试

**Files:**
- Create: `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_parser.py`
- Modify: `.agents/skills/video-to-slides/scripts/videotodoc/mindmap.py`（仅当测试暴露 bug 时）

**Interfaces:**
- Consumes: Mermaid `mindmap` 文本字符串
- Produces: `_MindmapNode` 树结构；`_parse_mermaid_tree(text: str) -> _MindmapNode | None`

- [ ] **Step 1: Write the failing test**

```python
from videotodoc.mindmap import _parse_mermaid_tree

SAMPLE_MMD = """mindmap
  root((Git + GitHub))
    基础概念
      Git
        开源免费
      GitHub
    环境准备
      安装工具
"""

def test_parse_mermaid_tree_structure():
    root = _parse_mermaid_tree(SAMPLE_MMD)
    assert root is not None
    assert root.text == "Git + GitHub"
    assert root.level == 0
    assert [c.text for c in root.children] == ["基础概念", "环境准备"]
    assert [c.text for c in root.children[0].children] == ["Git", "GitHub"]
    assert [c.text for c in root.children[0].children[0].children] == ["开源免费"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd .agents/skills/video-to-slides/scripts
PYTHONPATH=. python -m pytest videotodoc/tests/test_mindmap_parser.py -v
```

Expected: FAIL with `ModuleNotFoundError` or `ImportError` if test file path wrong; otherwise PASS (parser already exists).

- [ ] **Step 3: Fix import / path issues if any**

If import fails, add an empty `__init__.py` in `videotodoc/tests/` or adjust `PYTHONPATH`.

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
PYTHONPATH=. python -m pytest videotodoc/tests/test_mindmap_parser.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_parser.py
git commit -m "test(mindmap): add parser unit tests"
```

---

### Task 2: 新增多栏布局引擎模块

**Files:**
- Create: `.agents/skills/video-to-slides/scripts/videotodoc/mindmap_layout.py`
- Test: `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_layout.py`

**Interfaces:**
- Consumes: `_MindmapNode` from `mindmap.py`
- Produces:
  - `class MindmapLayout`
  - `LayoutNode = TypedDict(...)` with keys `text`, `level`, `x`, `y`, `width`, `height`, `children`
  - `compute_layout(root: _MindmapNode, config: LayoutConfig) -> MindmapLayout`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
PYTHONPATH=. python -m pytest videotodoc/tests/test_mindmap_layout.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'videotodoc.mindmap_layout'`

- [ ] **Step 3: Write minimal implementation**

Create `.agents/skills/video-to-slides/scripts/videotodoc/mindmap_layout.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
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
        min_leaf_gap: int = 14,
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
        self.min_leaf_gap = min_leaf_gap
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
    def __init__(self, root: LayoutNode, image_width: float, image_height: float) -> None:
        self.root_node = root
        self.image_width = image_width
        self.image_height = image_height

    @property
    def column_count(self) -> int:
        return len(self.root_node["children"])

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

    root_x = image_width / 2 - cfg.root_w / 2 if multi_column else cfg.margin_x
    root_y = cfg.margin_y if multi_column else image_height / 2 - cfg.root_h / 2

    root_layout = LayoutNode(
        text=root.text,
        level=0,
        x=root_x,
        y=root_y,
        width=cfg.root_w,
        height=cfg.root_h,
        children=col_layouts,
    )

    return MindmapLayout(root_layout, image_width, image_height)
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
PYTHONPATH=. python -m pytest videotodoc/tests/test_mindmap_layout.py -v
```

Expected: PASS (may need to tune assertion tolerances)

- [ ] **Step 5: Commit**

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/mindmap_layout.py \
        .agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_layout.py
git commit -m "feat(mindmap): add multi-column layout engine"
```

---

### Task 3: 使用新布局引擎重写 Python 渲染器

**Files:**
- Modify: `.agents/skills/video-to-slides/scripts/videotodoc/mindmap.py`
- Test: `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_render.py`

**Interfaces:**
- Consumes: `MindmapLayout` from `mindmap_layout.py`
- Produces: PNG image file at `image_path`

- [ ] **Step 1: Write the failing test**

```python
import tempfile
from pathlib import Path
from PIL import Image

from videotodoc.mindmap import _render_mindmap_with_python, _parse_mermaid_tree

SAMPLE = """mindmap
  root((Test))
    A
      a1
      a2
    B
      b1
"""

def test_render_creates_png():
    root = _parse_mermaid_tree(SAMPLE)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "mindmap.png"
        _render_mindmap_with_python_from_tree(root, out)
        assert out.exists()
        img = Image.open(out)
        assert img.format == "PNG"
        assert img.width > 0 and img.height > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
PYTHONPATH=. python -m pytest videotodoc/tests/test_mindmap_render.py -v
```

Expected: FAIL because `_render_mindmap_with_python_from_tree` does not exist.

- [ ] **Step 3: Write minimal implementation**

In `.agents/skills/video-to-slides/scripts/videotodoc/mindmap.py`:

1. Add imports at top:
```python
from .mindmap_layout import LayoutConfig, MindmapLayout, compute_layout, LayoutNode
```

2. Replace `_render_mindmap_with_python` body and helpers with:

```python
def _render_mindmap_with_python(mindmap_path: Path, image_path: Path) -> None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ModuleNotFoundError as exc:
        raise VideoToDocError("mmdc 渲染失败，且未安装 Pillow，无法使用 Python fallback。") from exc

    root = _parse_mermaid_tree(mindmap_path.read_text(encoding="utf-8"))
    if not root:
        raise VideoToDocError(f"mindmap.mmd 没有可渲染节点：{mindmap_path}")

    _render_mindmap_with_python_from_tree(root, image_path)


def _render_mindmap_with_python_from_tree(root: _MindmapNode, image_path: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    cfg = LayoutConfig()
    layout = compute_layout(root, cfg)
    img = Image.new("RGB", (int(layout.image_width), int(layout.image_height)), "white")
    draw = ImageDraw.Draw(img)
    font_root = _load_font(14)
    font_chapter = _load_font(12)
    font_leaf = _load_font(10)
    _draw_layout_node(draw, layout.root_node, font_root, font_chapter, font_leaf)
    image_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(image_path)


def _draw_layout_node(draw: ImageDraw.ImageDraw, node: LayoutNode, font_root, font_chapter, font_leaf) -> None:
    x, y, w, h = node["x"], node["y"], node["width"], node["height"]
    level = node["level"]
    if level == 0:
        fill, outline, font, color = "#4caf50", "#4caf50", font_root, "white"
        radius = 10
    elif level == 1:
        fill, outline, font, color = "#dbeafe", "#1c60af", font_chapter, "#1f2937"
        radius = 8
    else:
        fill, outline, font, color = "#f8fafc", "#cbd5e1", font_leaf, "#1f2937"
        radius = 5

    draw.rounded_rectangle([x, y, x + w, y + h], radius=radius, fill=fill, outline=outline, width=2 if level <= 1 else 1)
    text = _wrap_text(node["text"], 12 if level == 0 else (10 if level == 1 else 9))
    bbox = draw.multilinebbox((0, 0), text, font=font, spacing=2)
    text_h = bbox[3] - bbox[1]
    draw.multiline_text((x + w / 2, y + h / 2 - text_h / 2), text, fill=color, font=font, spacing=2, anchor="mm")

    for child in node["children"]:
        _draw_connection(draw, node, child)
        _draw_layout_node(draw, child, font_root, font_chapter, font_leaf)


def _draw_connection(draw: ImageDraw.ImageDraw, parent: LayoutNode, child: LayoutNode) -> None:
    px = parent["x"] + parent["width"]
    py = parent["y"] + parent["height"] / 2
    cx = child["x"]
    cy = child["y"] + child["height"] / 2
    mid_x = (px + cx) / 2
    draw.line([(px, py), (mid_x, py), (mid_x, cy), (cx, cy)], fill="#aac2e6", width=2, joint="curve")
```

3. Keep `_parse_mermaid_tree`, `_parse_mermaid_mindmap`, `_MindmapNode`, `_load_font`, `_wrap_text`. Remove old `_assign_positions`, `_draw_edges`, `_draw_nodes`, `_node_rect`, `_count_leaves`, `_max_level`.

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
PYTHONPATH=. python -m pytest videotodoc/tests/test_mindmap_render.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/mindmap.py \
        .agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_render.py
git commit -m "feat(mindmap): rewrite python renderer with directory-tree layout"
```

---

### Task 4: 将 Python 渲染器设为默认，Mermaid 改为可选

**Files:**
- Modify: `.agents/skills/video-to-slides/scripts/videotodoc/mindmap.py`
- Modify: `.agents/skills/video-to-slides/scripts/videotodoc/cli.py`（如果 `render-mindmap` 命令有 `--mermaid` 参数）

**Interfaces:**
- `render_mindmap_and_refresh_docs(run_dir, mindmap_path=None, image_path=None, use_mermaid=False)`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path
from unittest.mock import patch
from videotodoc.mindmap import render_mindmap_and_refresh_docs

def test_default_uses_python_renderer(tmp_path: Path):
    mmd = tmp_path / "mindmap.mmd"
    mmd.write_text("""mindmap\n  root((R))\n    A\n      a1\n""", encoding="utf-8")
    with patch("videotodoc.mindmap._render_mindmap_with_python") as mock_py, \
         patch("videotodoc.mindmap._run_mmdc") as mock_mmdc:
        render_mindmap_and_refresh_docs(tmp_path)
        assert mock_py.called
        assert not mock_mmdc.called
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
PYTHONPATH=. python -m pytest videotodoc/tests/test_mindmap_default.py -v
```

Expected: FAIL because current implementation calls `_run_mmdc` first.

- [ ] **Step 3: Write minimal implementation**

In `.agents/skills/video-to-slides/scripts/videotodoc/mindmap.py`:

```python
def render_mindmap_and_refresh_docs(
    run_dir: Path,
    mindmap_path: Path | None = None,
    image_path: Path | None = None,
    use_mermaid: bool = False,
) -> tuple[Path, list[Path]]:
    run_dir = run_dir.resolve()
    mindmap_path = mindmap_path or (run_dir / "mindmap.mmd")
    image_path = image_path or (run_dir / "mindmap.png")
    if not mindmap_path.exists():
        raise VideoToDocError(f"找不到 Mermaid 源文件：{mindmap_path}")

    if use_mermaid:
        mmdc = _find_mmdc()
        _run_mmdc([mmdc, "-i", str(mindmap_path), "-o", str(image_path), "-b", "transparent"])
    else:
        _render_mindmap_with_python(mindmap_path, image_path)

    refreshed: list[Path] = []
    for md_file in run_dir.glob("*.md"):
        if "质量报告" in md_file.name:
            continue
        ensure_mindmap_link(md_file, image_path)
        docx_file = md_file.with_suffix(".docx")
        if docx_file.exists():
            generated = markdown_to_docx(md_file, docx_file)
            if generated:
                refreshed.append(generated)
    return image_path, refreshed
```

If `cli.py` has a `--mermaid` flag, add it there too; otherwise skip.

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
PYTHONPATH=. python -m pytest videotodoc/tests/test_mindmap_default.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/mindmap.py \
        .agents/skills/video-to-slides/scripts/videotodoc/cli.py \
        .agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_default.py
git commit -m "feat(mindmap): make python renderer default, mermaid optional"
```

---

### Task 5: 端到端验证（使用真实 .mmd 产物）

**Files:**
- Modify: none
- Test: manual

- [ ] **Step 1: 找到最近一次 run 目录中的 .mmd**

Run:
```bash
cd /Users/jarvis/Documents/VideoToDoc-skills
ls -t runs/*/*.mmd | head -1
```

Expected: 输出类似 `runs/Git+Github.../Git_Github..._思维导图_....mmd`

- [ ] **Step 2: 手动运行 render_mindmap.py**

Run:
```bash
cd .agents/skills/video-to-slides/scripts
python3 render_mindmap.py /Users/jarvis/Documents/VideoToDoc-skills/runs/<run_dir>
```

Expected: 命令成功退出，生成新的 `mindmap.png`。

- [ ] **Step 3: 检查输出图片**

Run:
```bash
file runs/<run_dir>/mindmap.png
```

Expected: `PNG image data, ...`

- [ ] **Step 4: 视觉检查**

打开 `runs/<run_dir>/mindmap.png`，确认：
- 根节点在顶部居中（因为章节多、分栏）
- 一级章节为蓝色带框节点
- 二级/三级为白色带框节点
- 节点无重叠，连线为曲线或虚线
- 仍为单张 PNG

- [ ] **Step 5: Commit 验证产物（可选）**

如果结果正确，无需提交产物（runs/ 在 .gitignore 中）。

---

### Task 6: 更新文档说明

**Files:**
- Modify: `.agents/skills/video-to-slides/SKILL.md`
- Modify: `.agents/skills/video-to-slides/scripts/videotodoc/README.md`（如存在）

- [ ] **Step 1: 更新 SKILL.md 中关于思维导图的部分**

找到 SKILL.md 中“渲染导图”小节，更新为：

```markdown
### ⑨ 渲染导图

- 运行 `scripts/render_mindmap.py`
- 默认使用内置 Python 渲染器生成目录树状思维导图（多栏自适应）
- 如需旧版 Mermaid 圆形散射，可传 `--mermaid` 参数
- 将 `.mmd` 渲染为 `.png`
```

- [ ] **Step 2: 提交文档更新**

```bash
git add .agents/skills/video-to-slides/SKILL.md
git commit -m "docs(mindmap): update renderer docs"
```

---

## 自评检查

**Spec 覆盖检查：**

| Spec 要求 | 对应 Task |
|-----------|-----------|
| 章节逻辑优先 | Task 2（根节点 children 即章节） |
| 向右侧展开 | Task 2/3（子节点 x 递增） |
| 自动分栏 | Task 2（`_split_columns`） |
| 根节点自适应 | Task 2（multi_column 分支） |
| 节点加框 + 层级配色 | Task 3（`_draw_layout_node`） |
| 节点最小间距 | Task 2（`min_leaf_gap`, `chapter_gap`） |
| 跨栏虚线不穿过节点 | Task 3（连接逻辑） |
| 单张 PNG 输出 | Task 3/4（保持 image_path 输出） |
| 文本截断/换行 | Task 3（`_wrap_text` 复用） |
| 默认 Python，Mermaid 可选 | Task 4 |

**Placeholder 扫描：** 无 TBD/TODO。

**类型一致性：** `_MindmapNode` 由 parser 产出，layout 消费；`LayoutNode` 由 layout 产出，renderer 消费；签名一致。
