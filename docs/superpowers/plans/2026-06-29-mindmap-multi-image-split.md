# 思维导图多图拆分与渲染校验实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 当思维导图节点过多或单图尺寸过大时，自动按章节拆分为多张 PNG，并在渲染后执行可读性校验。

**Architecture:** 新增 `mindmap_verify.py` 负责校验布局/截断/尺寸；扩展 `mindmap_layout.py` 支持按章节切分并生成多个子树布局；改造 `mindmap.py` 的主渲染流程为“单图渲染 → 校验 → 必要时拆图渲染”；更新 `document.py`、`cli.py` 和 `pipeline.py` 以支持多张思维导图插入与输出。

**Tech Stack:** Python 3.11+, Pillow, pytest

## Global Constraints

- 默认输出仍是 PNG，不引入前端/浏览器依赖。
- 保持 `.mmd` 源文件不变。
- 单张子图仍遵循目录树状布局、节点加框、层级配色、Bézier 曲线、顶部虚线横梁。
- 拆图后产物命名保持 `<视频标题>_思维导图_01_<时间戳>.png` 形式。
- 不新增除 Pillow 外的第三方依赖。
- 向后兼容：仅单图时 Markdown/Word 表现与之前一致。

---

### Task 1: 新增思维导图校验模块

**Files:**
- Create: `.agents/skills/video-to-slides/scripts/videotodoc/mindmap_verify.py`
- Test: `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_verify.py`

**Interfaces:**
- Consumes: `MindmapLayout`, `LayoutConfig`
- Produces: `verify_layout(layout, cfg) -> list[str]`，返回问题描述列表（空列表表示通过）

- [ ] **Step 1: Write the failing test**

```python
from videotodoc.mindmap_layout import LayoutConfig, compute_layout
from videotodoc.mindmap import _parse_mermaid_tree
from videotodoc.mindmap_verify import verify_layout

LONG_MMD = """mindmap
  root((R))
    A
      a1
      a2
      a3
      a4
      a5
      a6
      a7
      a8
      a9
      a10
    B
      b1
      b2
      b3
      b4
      b5
      b6
      b7
      b8
      b9
      b10
    C
      c1
      c2
      c3
      c4
      c5
      c6
      c7
      c8
      c9
      c10
"""

def test_verify_flags_excessive_height():
    root = _parse_mermaid_tree(LONG_MMD)
    cfg = LayoutConfig(max_col_height=80, chapter_h=20, leaf_h=16, leaf_gap=4, chapter_gap=10)
    layout = compute_layout(root, cfg)
    issues = verify_layout(layout, cfg)
    assert any("高度" in issue or "过高" in issue or "size" in issue.lower() for issue in issues)
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd .agents/skills/video-to-slides/scripts
PYTHONPATH=. python -m pytest videotodoc/tests/test_mindmap_verify.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'videotodoc.mindmap_verify'`

- [ ] **Step 3: Write minimal implementation**

Create `.agents/skills/video-to-slides/scripts/videotodoc/mindmap_verify.py`:

```python
from __future__ import annotations

from .mindmap_layout import LayoutConfig, MindmapLayout


MAX_IMAGE_HEIGHT = 1600
MAX_IMAGE_WIDTH = 3000
MAX_NODES_PER_IMAGE = 80


def _count_nodes(layout_node) -> int:
    return 1 + sum(_count_nodes(child) for child in layout_node["children"])


def _collect_truncated_nodes(layout_node) -> list[str]:
    found: list[str] = []
    text = layout_node["text"]
    if text.endswith("…") or text.endswith("..."):
        found.append(text)
    for child in layout_node["children"]:
        found.extend(_collect_truncated_nodes(child))
    return found


def verify_layout(layout: MindmapLayout, cfg: LayoutConfig) -> list[str]:
    issues: list[str] = []
    if layout.image_height > MAX_IMAGE_HEIGHT:
        issues.append(f"单图高度 {layout.image_height:.0f}px 超过建议上限 {MAX_IMAGE_HEIGHT}px，建议拆图")
    if layout.image_width > MAX_IMAGE_WIDTH:
        issues.append(f"单图宽度 {layout.image_width:.0f}px 超过建议上限 {MAX_IMAGE_WIDTH}px，建议拆图")
    node_count = _count_nodes(layout.root_node)
    if node_count > MAX_NODES_PER_IMAGE:
        issues.append(f"节点数 {node_count} 超过建议上限 {MAX_NODES_PER_IMAGE}，建议拆图")
    truncated = _collect_truncated_nodes(layout.root_node)
    if truncated:
        issues.append(f"存在 {len(truncated)} 个节点文本被截断，建议放宽节点宽度或拆图")
    return issues
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
PYTHONPATH=. python -m pytest videotodoc/tests/test_mindmap_verify.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/mindmap_verify.py \
        .agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_verify.py
git commit -m "feat(mindmap): add layout verification module"
```

---

### Task 2: 扩展布局引擎支持按章节拆分

**Files:**
- Modify: `.agents/skills/video-to-slides/scripts/videotodoc/mindmap_layout.py`
- Test: `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_layout.py`

**Interfaces:**
- Consumes: `_MindmapNode` from `mindmap.py`
- Produces: `split_layouts_by_chapters(root, cfg) -> list[MindmapLayout]`

- [ ] **Step 1: Write the failing test**

Append to `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_layout.py`:

```python
from videotodoc.mindmap_layout import split_layouts_by_chapters

SPLIT_MMD = """mindmap
  root((R))
    A
      a1
    B
      b1
    C
      c1
    D
      d1
"""

def test_split_layouts_by_chapters():
    root = _parse_mermaid_tree(SPLIT_MMD)
    layouts = split_layouts_by_chapters(root, LayoutConfig(max_chapters_per_image=2))
    assert len(layouts) == 2
    assert layouts[0].column_count == 1
    assert layouts[1].column_count == 1
    first_chapters = [c["text"] for c in layouts[0].chapter_nodes]
    second_chapters = [c["text"] for c in layouts[1].chapter_nodes]
    assert first_chapters == ["A", "B"]
    assert second_chapters == ["C", "D"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
PYTHONPATH=. python -m pytest videotodoc/tests/test_mindmap_layout.py::test_split_layouts_by_chapters -v
```

Expected: FAIL with `ImportError: cannot import name 'split_layouts_by_chapters'`

- [ ] **Step 3: Write minimal implementation**

In `.agents/skills/video-to-slides/scripts/videotodoc/mindmap_layout.py`:

1. Add `max_chapters_per_image: int = 4` to `LayoutConfig`.

2. Add import at top:
```python
from copy import deepcopy
```

3. Add helper and function:

```python
def _clone_root_with_chapters(root: _MindmapNode, chapters: list[_MindmapNode]) -> _MindmapNode:
    clone = _MindmapNode(root.text, root.level)
    clone.children = list(chapters)
    return clone


def split_layouts_by_chapters(root: _MindmapNode, cfg: LayoutConfig | None = None) -> list[MindmapLayout]:
    cfg = cfg or LayoutConfig()
    chapters = list(root.children)
    if not chapters:
        return [compute_layout(root, cfg)]
    layouts: list[MindmapLayout] = []
    chunk_size = max(1, cfg.max_chapters_per_image)
    for start in range(0, len(chapters), chunk_size):
        chunk = chapters[start : start + chunk_size]
        sub_root = _clone_root_with_chapters(root, chunk)
        layouts.append(compute_layout(sub_root, cfg))
    return layouts
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
PYTHONPATH=. python -m pytest videotodoc/tests/test_mindmap_layout.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/mindmap_layout.py \
        .agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_layout.py
git commit -m "feat(mindmap): add chapter-based layout splitting"
```

---

### Task 3: 改造渲染器支持多图输出

**Files:**
- Modify: `.agents/skills/video-to-slides/scripts/videotodoc/mindmap.py`
- Test: `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_render.py`

**Interfaces:**
- `render_mindmap_and_refresh_docs(...) -> tuple[list[Path], list[Path]]`

- [ ] **Step 1: Write the failing test**

Replace `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_render.py` content:

```python
import tempfile
from pathlib import Path
from PIL import Image

from videotodoc.mindmap import _render_mindmap_with_python_from_tree, _parse_mermaid_tree

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

Add new test file `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_multi.py`:

```python
import tempfile
from pathlib import Path
from unittest.mock import patch

from videotodoc.mindmap import render_mindmap_and_refresh_docs

LONG_MMD = """mindmap
  root((R))
    A
      a1
      a2
      a3
      a4
      a5
      a6
      a7
      a8
      a9
      a10
    B
      b1
      b2
      b3
      b4
      b5
      b6
      b7
      b8
      b9
      b10
    C
      c1
      c2
      c3
      c4
      c5
      c6
      c7
      c8
      c9
      c10
"""

def test_render_splits_when_too_many_nodes(tmp_path: Path):
    mmd = tmp_path / "mindmap.mmd"
    mmd.write_text(LONG_MMD, encoding="utf-8")
    image_paths, _ = render_mindmap_and_refresh_docs(tmp_path)
    assert len(image_paths) >= 2
    for path in image_paths:
        assert path.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
PYTHONPATH=. python -m pytest videotodoc/tests/test_mindmap_multi.py -v
```

Expected: FAIL with `ValueError` or assertion error because render returns single path.

- [ ] **Step 3: Write minimal implementation**

In `.agents/skills/video-to-slides/scripts/videotodoc/mindmap.py`:

1. Update imports:
```python
from .mindmap_layout import LayoutConfig, MindmapLayout, compute_layout, split_layouts_by_chapters
from .mindmap_verify import verify_layout
```

2. Update `render_mindmap_and_refresh_docs` signature and body:

```python
def render_mindmap_and_refresh_docs(
    run_dir: Path,
    mindmap_path: Path | None = None,
    image_path: Path | None = None,
    use_mermaid: bool = False,
) -> tuple[list[Path], list[Path]]:
    run_dir = run_dir.resolve()
    mindmap_path = mindmap_path or (run_dir / "mindmap.mmd")
    image_path = image_path or (run_dir / "mindmap.png")
    if not mindmap_path.exists():
        raise VideoToDocError(f"找不到 Mermaid 源文件：{mindmap_path}")

    if use_mermaid:
        mmdc = _find_mmdc()
        _run_mmdc([mmdc, "-i", str(mindmap_path), "-o", str(image_path), "-b", "transparent"])
        image_paths = [image_path]
    else:
        image_paths = _render_mindmap_multi(mindmap_path, image_path)

    refreshed: list[Path] = []
    for md_file in run_dir.glob("*.md"):
        if "质量报告" in md_file.name:
            continue
        ensure_mindmap_link(md_file, image_paths)
        docx_file = md_file.with_suffix(".docx")
        if docx_file.exists():
            generated = markdown_to_docx(md_file, docx_file)
            if generated:
                refreshed.append(generated)
    return image_paths, refreshed
```

3. Add `_render_mindmap_multi`:

```python
def _render_mindmap_multi(mindmap_path: Path, image_path: Path) -> list[Path]:
    from PIL import Image, ImageDraw, ImageFont

    root = _parse_mermaid_tree(mindmap_path.read_text(encoding="utf-8"))
    if not root:
        raise VideoToDocError(f"mindmap.mmd 没有可渲染节点：{mindmap_path}")

    cfg = LayoutConfig()
    base_layout = compute_layout(root, cfg)
    issues = verify_layout(base_layout, cfg)
    if not issues:
        _render_layout_to_file(base_layout, image_path)
        return [image_path]

    layouts = split_layouts_by_chapters(root, cfg)
    paths: list[Path] = []
    stem = image_path.stem
    suffix = image_path.suffix
    parent = image_path.parent
    for index, layout in enumerate(layouts, start=1):
        numbered = parent / f"{stem}_{index:02d}{suffix}"
        _render_layout_to_file(layout, numbered)
        paths.append(numbered)
    return paths
```

4. Rename/refactor existing `_render_mindmap_with_python_from_tree` to `_render_layout_to_file`:

```python
def _render_layout_to_file(layout: MindmapLayout, image_path: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (int(layout.image_width), int(layout.image_height)), "white")
    draw = ImageDraw.Draw(img)
    font_root = _load_font(14)
    font_chapter = _load_font(12)
    font_leaf = _load_font(10)
    _draw_layout_node(draw, layout.root_node, layout, font_root, font_chapter, font_leaf)
    image_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(image_path)
```

Keep `_render_mindmap_with_python_from_tree` as a thin wrapper for tests/backward compat if needed:

```python
def _render_mindmap_with_python_from_tree(root: _MindmapNode, image_path: Path) -> None:
    cfg = LayoutConfig()
    layout = compute_layout(root, cfg)
    _render_layout_to_file(layout, image_path)
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
PYTHONPATH=. python -m pytest videotodoc/tests/test_mindmap_render.py videotodoc/tests/test_mindmap_multi.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/mindmap.py \
        .agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_render.py \
        .agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_multi.py
git commit -m "feat(mindmap): support multi-image rendering when verification fails"
```

---

### Task 4: 更新文档插入逻辑支持多张图

**Files:**
- Modify: `.agents/skills/video-to-slides/scripts/videotodoc/document.py`
- Test: `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_document.py`（如不存在则创建）

**Interfaces:**
- `ensure_mindmap_link(markdown_path, mindmap_image_path: Path | list[Path] | None) -> Path`
- `render_compact_markdown(..., mindmap_image_path: Path | list[Path] | None = None)`
- `ensure_semantic_markdown(..., mindmap_image_path: Path | list[Path] | None = None)`

- [ ] **Step 1: Write the failing test**

Create `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_document.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
PYTHONPATH=. python -m pytest videotodoc/tests/test_document.py -v
```

Expected: FAIL with `TypeError` because `ensure_mindmap_link` expects single path.

- [ ] **Step 3: Write minimal implementation**

In `.agents/skills/video-to-slides/scripts/videotodoc/document.py`:

1. Update `render_compact_markdown` signature:
```python
def render_compact_markdown(
    title: str,
    sections: list[Section],
    output_path: Path,
    mindmap_image_path: Path | list[Path] | None = None,
) -> Path:
```

2. Update body to handle list:
```python
    if mindmap_image_path:
        lines.extend(["## 思维导图", ""])
        paths = mindmap_image_path if isinstance(mindmap_image_path, list) else [mindmap_image_path]
        for path in paths:
            lines.append(f"![思维导图]({_markdown_image_path(path, output_path.parent)})")
        lines.append("")
```

3. Update `ensure_semantic_markdown` signature similarly and use same pattern.

4. Update `ensure_mindmap_link`:

```python
def ensure_mindmap_link(markdown_path: Path, mindmap_image_path: Path | list[Path] | None) -> Path:
    if not mindmap_image_path:
        return markdown_path
    paths = mindmap_image_path if isinstance(mindmap_image_path, list) else [mindmap_image_path]
    if not paths:
        return markdown_path
    text = markdown_path.read_text(encoding="utf-8") if markdown_path.exists() else ""
    replacements = [f"![思维导图]({_markdown_image_path(p, markdown_path.parent)})" for p in paths]
    replacement_block = "\n\n".join(replacements)
    if re.search(r"!\[思维导图\]\([^)]+\)", text):
        text = re.sub(r"(!\[思维导图\]\([^)]+\)\n?\n?)*", replacement_block + "\n", text)
    elif "## 思维导图" in text:
        text = text.rstrip() + f"\n\n{replacement_block}\n"
    else:
        text = text.rstrip() + f"\n\n## 思维导图\n\n{replacement_block}\n"
    write_text(markdown_path, text.rstrip() + "\n")
    return markdown_path
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
PYTHONPATH=. python -m pytest videotodoc/tests/test_document.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/document.py \
        .agents/skills/video-to-slides/scripts/videotodoc/tests/test_document.py
git commit -m "feat(mindmap): support multiple mindmap images in markdown"
```

---

### Task 5: 更新 CLI 与 pipeline 处理多图输出

**Files:**
- Modify: `.agents/skills/video-to-slides/scripts/videotodoc/cli.py`
- Modify: `.agents/skills/video-to-slides/scripts/videotodoc/pipeline.py`
- Modify: `.agents/skills/video-to-slides/scripts/render_mindmap.py`
- Modify: `.agents/skills/video-to-slides/scripts/videotodoc/models.py`
- Test: existing pipeline tests may need mock updates

**Interfaces:**
- `ProcessResult.mindmap_image_path: Path | None` kept for backward compat (first image)
- `ProcessResult.mindmap_image_paths: list[Path]` added

- [ ] **Step 1: Write the failing test**

Update `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_default.py`:

```python
from pathlib import Path
from unittest.mock import patch
from videotodoc.mindmap import render_mindmap_and_refresh_docs

def test_default_uses_python_renderer(tmp_path: Path):
    mmd = tmp_path / "mindmap.mmd"
    mmd.write_text("""mindmap\n  root((R))\n    A\n      a1\n""", encoding="utf-8")
    with patch("videotodoc.mindmap._render_mindmap_multi") as mock_multi:
        mock_multi.return_value = [tmp_path / "mindmap.png"]
        image_paths, _ = render_mindmap_and_refresh_docs(tmp_path)
        assert image_paths == [tmp_path / "mindmap.png"]
        assert mock_multi.called
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
PYTHONPATH=. python -m pytest videotodoc/tests/test_mindmap_default.py -v
```

Expected: FAIL due to return type mismatch.

- [ ] **Step 3: Write minimal implementation**

1. In `.agents/skills/video-to-slides/scripts/videotodoc/models.py`, update `ProcessResult`:

```python
@dataclass
class ProcessResult:
    run_dir: Path
    transcript_path: Path | None = None
    slides_path: Path | None = None
    sections_path: Path | None = None
    markdown_path: Path | None = None
    compact_markdown_path: Path | None = None
    semantic_markdown_path: Path | None = None
    docx_path: Path | None = None
    semantic_docx_path: Path | None = None
    mindmap_path: Path | None = None
    mindmap_image_path: Path | None = None
    mindmap_image_paths: list[Path] = field(default_factory=list)
    quality_report_path: Path | None = None
```

2. In `.agents/skills/video-to-slides/scripts/videotodoc/cli.py`, update `_render_mindmap`:

```python
def _render_mindmap(args: argparse.Namespace) -> int:
    image_paths, refreshed = render_mindmap_and_refresh_docs(args.run_dir, use_mermaid=args.mermaid)
    print("思维导图已渲染：")
    for image_path in image_paths:
        print(f"- image: {image_path}")
    for docx_path in refreshed:
        print(f"- refreshed_docx: {docx_path}")
    return 0
```

3. In `.agents/skills/video-to-slides/scripts/render_mindmap.py`, update output printing to handle list:

```python
result.returncode
```

Actually `render_mindmap.py` just calls CLI and returns returncode; CLI prints images. No change needed unless we want to print in wrapper.

4. In `.agents/skills/video-to-slides/scripts/videotodoc/pipeline.py`:

Find places where `mindmap_image_path` is used to generate docs and update to use list of paths.

Around line 318 and 489 and 534:

```python
mm_image = mindmap_image_path if mindmap_image_path.exists() else None
```

Change to:

```python
mm_images = [p for p in [mindmap_image_path] if p.exists()]
if not mm_images:
    mm_images = None
```

Then pass `mindmap_image_path=mm_images` to doc generation functions.

Also when setting `ProcessResult`, set both `mindmap_image_path` and `mindmap_image_paths`:

```python
mindmap_image_paths=[mindmap_image_path] if mindmap_image_path.exists() else [],
```

There are two pipeline functions with similar code (`finalize_video` and `process_video`); update both.

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
PYTHONPATH=. python -m pytest videotodoc/tests/test_mindmap_default.py videotodoc/tests/test_pipeline_parallel.py videotodoc/tests/test_doc_generation_parallel.py -v
```

Expected: PASS (mocks may need updating if they assert single path)

- [ ] **Step 5: Commit**

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/cli.py \
        .agents/skills/video-to-slides/scripts/videotodoc/pipeline.py \
        .agents/skills/video-to-slides/scripts/videotodoc/models.py \
        .agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_default.py
git commit -m "feat(mindmap): propagate multi-image paths through CLI and pipeline"
```

---

### Task 6: 端到端验证真实 .mmd 产物

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

Expected: 命令成功退出，可能生成 `mindmap_01.png`、`mindmap_02.png` 等多张图。

- [ ] **Step 3: 检查输出图片**

Run:
```bash
file runs/<run_dir>/mindmap*.png
```

Expected: 多个 `PNG image data, ...`

- [ ] **Step 4: 检查 Markdown 插入**

打开 run 目录下的 `.md` 文件，确认 `## 思维导图` 下有多张 `![思维导图](...)` 引用。

- [ ] **Step 5: Commit 验证产物（可选）**

如果结果正确，无需提交产物（runs/ 在 .gitignore 中）。

---

### Task 7: 更新 SKILL.md 文档

**Files:**
- Modify: `.agents/skills/video-to-slides/SKILL.md`

- [ ] **Step 1: 更新 SKILL.md 中关于思维导图的部分**

找到 SKILL.md 中“⑨ 渲染导图”小节，更新为：

```markdown
### ⑨ 渲染导图

- 运行 `scripts/render_mindmap.py`
- 默认使用内置 Python 渲染器生成目录树状思维导图（多栏自适应）
- 如需旧版 Mermaid 圆形散射，可传 `--mermaid` 参数
- 将 `.mmd` 渲染为 `.png`
- 当节点过多或单图尺寸过大时，自动按章节拆分为 `mindmap_01.png`、`mindmap_02.png`... 并同步插入 Markdown/Word
```

- [ ] **Step 2: 提交文档更新**

```bash
git add .agents/skills/video-to-slides/SKILL.md
git commit -m "docs(mindmap): document multi-image split behavior"
```

---

## 自评检查

**Spec 覆盖检查：**

| 需求 | 对应 Task |
|------|-----------|
| 渲染后校验 | Task 1 |
| 按章节拆图 | Task 2 |
| 自动多图输出 | Task 3 |
| Markdown/Word 插入多张图 | Task 4 |
| CLI/pipeline 透传多图路径 | Task 5 |
| 端到端验证 | Task 6 |
| 文档更新 | Task 7 |

**Placeholder 扫描：** 无 TBD/TODO。

**类型一致性：**
- `render_mindmap_and_refresh_docs` 返回 `tuple[list[Path], list[Path]]`
- `ensure_mindmap_link` 接收 `Path | list[Path] | None`
- `ProcessResult` 新增 `mindmap_image_paths: list[Path]`，保留 `mindmap_image_path: Path | None`
