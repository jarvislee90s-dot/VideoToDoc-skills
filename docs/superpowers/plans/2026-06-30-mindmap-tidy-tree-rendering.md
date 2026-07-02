# 思维导图渲染重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把基于 Python Pillow 的思维导图渲染彻底替换为 Mermaid `tidy-tree` 布局渲染，添加章节序号、按章节自动拆图、渲染后规则校验，并保证 Markdown/Word 多图引用正确。

**Architecture:** 用 Mermaid CLI (`mmdc`) 作为唯一渲染后端；Python 负责 `.mmd` 预处理（注入 `tidy-tree` frontmatter、章节加序号、按章节拆分）、调用 mmdc 渲染、PNG 尺寸校验。彻底移除 Python Pillow 手动绘制路径。

**Tech Stack:** Python 3.12, Mermaid CLI (`mmdc`), PIL（仅用于 PNG 尺寸校验）, pytest

## Global Constraints

- 默认使用 Mermaid `tidy-tree` 布局，不再提供 Python Pillow 渲染选项
- 不调用视觉模型或云端多模态 API 做校验
- 单图尺寸 ≤ 3000×3000px，单图节点数 ≤ 80
- 拆分子图至少包含 2 个章节或 10 个节点
- 1 级章节标题必须带序号，如 "1. 基础概念"
- 现有 `render_mindmap_and_refresh_docs(run_dir, mindmap_path, image_path)` 函数签名保持不变
- 所有改动必须伴随测试，遵循 TDD

---

### Task 1: 创建 Mermaid 预处理模块 `mindmap_mermaid.py`

**Files:**
- Create: `.agents/skills/video-to-slides/scripts/videotodoc/mindmap_mermaid.py`
- Test: `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_mermaid.py`

**Interfaces:**
- Consumes: Mermaid mindmap 文本（字符串）
- Produces:
  - `inject_tidy_tree_config(mmd_text: str) -> str`
  - `add_chapter_numbers(mmd_text: str) -> str`
  - `split_mmd_by_chapters(mmd_text: str, max_nodes: int = 80, min_chapters: int = 2, min_nodes: int = 10) -> list[str]`
  - `count_nodes(mmd_text: str) -> int`

- [ ] **Step 1: 编写测试 `test_inject_tidy_tree_config`**

```python
def test_inject_tidy_tree_config():
    text = "mindmap\n  root((R))\n    A\n"
    result = inject_tidy_tree_config(text)
    assert result.startswith("---\nconfig:\n  layout: tidy-tree\n---\n\n")
    assert "mindmap\n  root((R))\n    A\n" in result
```

Run: `pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_mermaid.py::test_inject_tidy_tree_config -v`
Expected: FAIL with `inject_tidy_tree_config not defined`

- [ ] **Step 2: 实现 `inject_tidy_tree_config`**

```python
def inject_tidy_tree_config(mmd_text: str) -> str:
    frontmatter = "---\nconfig:\n  layout: tidy-tree\n---\n\n"
    return frontmatter + mmd_text.lstrip()
```

- [ ] **Step 3: 运行测试确认通过**

Run: `pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_mermaid.py::test_inject_tidy_tree_config -v`
Expected: PASS

- [ ] **Step 4: 编写测试 `test_add_chapter_numbers`**

```python
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
```

Run: `pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_mermaid.py::test_add_chapter_numbers -v`
Expected: FAIL

- [ ] **Step 5: 实现 `add_chapter_numbers`**

```python
import re


def add_chapter_numbers(mmd_text: str) -> str:
    lines = mmd_text.splitlines()
    chapter_index = 0
    result: list[str] = []
    for line in lines:
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if indent == 4 and stripped and not stripped.startswith("root"):
            chapter_index += 1
            line = f"{line[:indent]}{chapter_index}. {stripped}"
        result.append(line)
    return "\n".join(result) + "\n"
```

- [ ] **Step 6: 运行测试确认通过**

Run: `pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_mermaid.py::test_add_chapter_numbers -v`
Expected: PASS

- [ ] **Step 7: 编写测试 `test_split_mmd_by_chapters`**

```python
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
    parts = split_mmd_by_chapters(text, max_nodes=4, min_chapters=2, min_nodes=1)
    assert len(parts) == 2
    assert "1. A" in parts[0] and "2. B" in parts[0]
    assert "3. C" in parts[1]
```

Run: `pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_mermaid.py::test_split_mmd_by_chapters -v`
Expected: FAIL

- [ ] **Step 8: 实现 `split_mmd_by_chapters` 和 `count_nodes`**

```python
def count_nodes(mmd_text: str) -> int:
    """统计 mindmap 中的节点数量（包含根节点）。"""
    count = 0
    for line in mmd_text.splitlines():
        stripped = line.strip()
        if stripped and stripped != "mindmap" and not stripped.startswith("---") and not stripped.startswith("config"):
            count += 1
    return count


def split_mmd_by_chapters(
    mmd_text: str,
    max_nodes: int = 80,
    min_chapters: int = 2,
    min_nodes: int = 10,
) -> list[str]:
    lines = mmd_text.splitlines()
    root_lines: list[str] = []
    chapters: list[list[str]] = []
    current_chapter: list[str] | None = None

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped == "mindmap":
            continue
        if stripped.startswith("root"):
            root_lines.append(line)
            continue
        indent = len(line) - len(line.lstrip())
        if indent == 4:
            if current_chapter is not None:
                chapters.append(current_chapter)
            current_chapter = [line]
        elif current_chapter is not None and indent > 4:
            current_chapter.append(line)
        else:
            root_lines.append(line)
    if current_chapter:
        chapters.append(current_chapter)

    if not chapters:
        return [mmd_text]

    total_nodes = count_nodes(mmd_text)
    if total_nodes <= max_nodes and len(chapters) >= min_chapters:
        return [mmd_text]

    # 计算每章节点数，尽量合并小章节以满足 min_nodes / min_chapters
    chunks: list[list[list[str]]] = []
    current_chunk: list[list[str]] = []
    current_nodes = 0

    def chapter_node_count(ch: list[str]) -> int:
        return 1 + sum(1 for line in ch if len(line) - len(line.lstrip()) > 4)

    for ch in chapters:
        cn = chapter_node_count(ch)
        if not current_chunk:
            current_chunk.append(ch)
            current_nodes += cn
        elif current_nodes + cn <= max_nodes and len(current_chunk) < min_chapters:
            current_chunk.append(ch)
            current_nodes += cn
        elif current_nodes < min_nodes and current_nodes + cn <= max_nodes:
            current_chunk.append(ch)
            current_nodes += cn
        else:
            chunks.append(current_chunk)
            current_chunk = [ch]
            current_nodes = cn
    if current_chunk:
        chunks.append(current_chunk)

    # 合并尾部过小的 chunk
    while len(chunks) >= 2:
        last = chunks[-1]
        second_last = chunks[-2]
        last_nodes = sum(chapter_node_count(ch) for ch in last)
        second_last_nodes = sum(chapter_node_count(ch) for ch in second_last)
        if last_nodes < min_nodes and second_last_nodes + last_nodes <= max_nodes:
            chunks[-2] = second_last + last
            chunks.pop()
        else:
            break

    result: list[str] = []
    for chunk in chunks:
        body = "\n".join(root_lines + [line for ch in chunk for line in ch])
        result.append(f"mindmap\n{body}\n")
    return result
```

- [ ] **Step 9: 运行测试确认通过**

Run: `pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_mermaid.py -v`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/mindmap_mermaid.py \
        .agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_mermaid.py
git commit -m "feat(mindmap): add mermaid preprocessing for tidy-tree, chapter numbers, and split"
```

---

### Task 2: 重写 `mindmap.py` 为 Mermaid-only 渲染

**Files:**
- Modify: `.agents/skills/video-to-slides/scripts/videotodoc/mindmap.py`
- Test: `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_render.py`

**Interfaces:**
- Consumes: `mindmap_mermaid.inject_tidy_tree_config`, `add_chapter_numbers`, `split_mmd_by_chapters`
- Produces: `render_mindmap_and_refresh_docs(run_dir, mindmap_path, image_path) -> tuple[list[Path], list[Path]]`（签名不变，内部实现全改）

- [ ] **Step 1: 编写新测试 `test_render_uses_tidy_tree_config`**

```python
from pathlib import Path
from unittest.mock import patch


def test_render_uses_tidy_tree_config(tmp_path: Path):
    mmd = tmp_path / "mindmap.mmd"
    mmd.write_text("mindmap\n  root((R))\n    A\n      a1\n", encoding="utf-8")

    captured: list[str] = []

    def fake_run_mmdc(args: list[str]) -> None:
        input_path = Path(args[args.index("-i") + 1])
        output_path = Path(args[args.index("-o") + 1])
        captured.append(input_path.read_text(encoding="utf-8"))
        from PIL import Image
        img = Image.new("RGBA", (100, 100), (255, 255, 255, 0))
        img.save(output_path)

    with patch("videotodoc.mindmap._run_mmdc", side_effect=fake_run_mmdc):
        image_paths, _ = render_mindmap_and_refresh_docs(tmp_path)

    assert len(image_paths) == 1
    assert "layout: tidy-tree" in captured[0]
    assert "1. A" in captured[0]
```

Run: `pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_render.py::test_render_uses_tidy_tree_config -v`
Expected: FAIL

- [ ] **Step 2: 重写 `render_mindmap_and_refresh_docs` 和相关辅助函数**

把 `mindmap.py` 中以下内容替换：

```python
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from PIL import Image

from .document import ensure_mindmap_link, markdown_to_docx
from .mindmap_mermaid import add_chapter_numbers, inject_tidy_tree_config, split_mmd_by_chapters
from .utils import VideoToDocError


def render_mindmap_and_refresh_docs(
    run_dir: Path,
    mindmap_path: Path | None = None,
    image_path: Path | None = None,
    use_mermaid: bool = False,
) -> tuple[list[Path], list[Path]]:
    """使用 Mermaid tidy-tree 渲染思维导图，并刷新所有 Markdown/Word 文档。"""
    run_dir = run_dir.resolve()
    mindmap_path = mindmap_path or (run_dir / "mindmap.mmd")
    image_path = image_path or (run_dir / "mindmap.png")
    if not mindmap_path.exists():
        raise VideoToDocError(f"找不到 Mermaid 源文件：{mindmap_path}")

    raw_text = mindmap_path.read_text(encoding="utf-8")
    numbered = add_chapter_numbers(raw_text)
    sub_mmds = split_mmd_by_chapters(numbered)

    image_paths: list[Path] = []
    stem = image_path.stem
    suffix = image_path.suffix
    parent = image_path.parent
    mmdc = _find_mmdc()

    for index, sub_mmd in enumerate(sub_mmds, start=1):
        prepared = inject_tidy_tree_config(sub_mmd)
        sub_path = parent / f"{stem}_{index:02d}.mmd"
        png_path = parent / f"{stem}_{index:02d}{suffix}"
        sub_path.write_text(prepared, encoding="utf-8")
        _run_mmdc([mmdc, "-i", str(sub_path), "-o", str(png_path), "-b", "transparent"])
        _verify_png_size(png_path)
        image_paths.append(png_path)

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


def _verify_png_size(png_path: Path, max_size: int = 3000) -> None:
    with Image.open(png_path) as img:
        if img.width > max_size or img.height > max_size:
            raise VideoToDocError(
                f"思维导图尺寸过大：{img.width}x{img.height}px，超过 {max_size}px"
            )


def _find_mmdc() -> str:
    found = shutil.which("mmdc")
    if found:
        return found
    user_tools = Path.home() / ".tools" / "bin" / "mmdc"
    if user_tools.exists():
        return str(user_tools)
    local = Path("node_modules/.bin/mmdc")
    if local.exists():
        return str(local)
    bundled = Path(".tools/mermaid-cli/node_modules/.bin/mmdc")
    if bundled.exists():
        return str(bundled)
    raise VideoToDocError(
        "找不到 mmdc。请先安装 Mermaid CLI：npm install -g @mermaid-js/mermaid-cli，"
        "或在项目内安装：npm install --prefix .tools/mermaid-cli @mermaid-js/mermaid-cli"
    )


def _run_mmdc(args: list[str]) -> None:
    env = _mmdc_env()
    try:
        subprocess.run(
            args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, env=env, timeout=120,
        )
    except FileNotFoundError as exc:
        raise VideoToDocError(f"找不到命令：{args[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        cmd_str = " ".join(args)
        details = ""
        if exc.stderr:
            stderr_text = exc.stderr if isinstance(exc.stderr, str) else exc.stderr.decode("utf-8", errors="replace")
            if stderr_text.strip():
                details = f"\nstderr: {stderr_text.strip()}"
        elif exc.stdout:
            stdout_text = exc.stdout if isinstance(exc.stdout, str) else exc.stdout.decode("utf-8", errors="replace")
            if stdout_text.strip():
                details = f"\nstdout: {stdout_text.strip()}"
        raise VideoToDocError(f"命令执行超时（120s）：{cmd_str}{details}") from exc
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or exc.stdout.strip()
        raise VideoToDocError(f"命令执行失败：{' '.join(args)}\n{message}") from exc


def _mmdc_env() -> dict[str, str]:
    import os

    env = dict(os.environ)
    if "PUPPETEER_EXECUTABLE_PATH" not in env:
        chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        chromium = Path("/Applications/Chromium.app/Contents/MacOS/Chromium")
        if chrome.exists():
            env["PUPPETEER_EXECUTABLE_PATH"] = str(chrome)
        elif chromium.exists():
            env["PUPPETEER_EXECUTABLE_PATH"] = str(chromium)
    return env
```

- [ ] **Step 3: 运行新测试**

Run: `pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_render.py::test_render_uses_tidy_tree_config -v`
Expected: PASS

- [ ] **Step 4: 编写测试 `test_render_splits_large_mindmap`**

```python
def test_render_splits_large_mindmap(tmp_path: Path):
    lines = ["mindmap", "  root((R))"]
    for i in range(30):
        lines.append(f"    Ch{i}")
        for j in range(3):
            lines.append(f"      leaf{i}_{j}")
    mmd = tmp_path / "mindmap.mmd"
    mmd.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def fake_run_mmdc(args: list[str]) -> None:
        output_path = Path(args[args.index("-o") + 1])
        from PIL import Image
        img = Image.new("RGBA", (100, 100), (255, 255, 255, 0))
        img.save(output_path)

    with patch("videotodoc.mindmap._run_mmdc", side_effect=fake_run_mmdc):
        image_paths, _ = render_mindmap_and_refresh_docs(tmp_path)

    assert len(image_paths) >= 2
```

Run: `pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_render.py::test_render_splits_large_mindmap -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/mindmap.py \
        .agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_render.py
git commit -m "feat(mindmap): replace Python renderer with Mermaid tidy-tree"
```

---

### Task 3: 更新 `generate_mindmap` 的 fallback 路径

**Files:**
- Modify: `.agents/skills/video-to-slides/scripts/videotodoc/document.py:202-223`
- Test: `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_document.py`

**Interfaces:**
- Consumes: `Settings`, `Section`
- Produces: `generate_mindmap(...)` 输出的 `.mmd` 带章节序号且语法正确

- [ ] **Step 1: 编写测试 `test_generate_mindmap_adds_chapter_numbers`**

```python
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
```

Run: `pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_document.py::test_generate_mindmap_adds_chapter_numbers -v`
Expected: FAIL

- [ ] **Step 2: 修改 `generate_mindmap` fallback 路径**

把 `document.py` 中 fallback 的这部分：

```python
    lines = ["mindmap", f"  root(({_safe_mermaid(title)}))"]
    for section in sections[:20]:
        heading = _extract_heading(section.transcript, section.slide_index)
        lines.append(f"    第 {section.slide_index} 页")
        lines.append(f"      {_safe_mermaid(heading)}")
    if len(sections) > 20:
        lines.append("    更多页面")
        lines.append(f"      共 {len(sections)} 页，详见正文")
    mindmap = "\n".join(lines)
```

改为：

```python
    lines = ["mindmap", f"  root(({_safe_mermaid(title)}))"]
    for index, section in enumerate(sections[:20], start=1):
        heading = _extract_heading(section.transcript, section.slide_index)
        lines.append(f"    {index}. 第 {section.slide_index} 页")
        lines.append(f"      {_safe_mermaid(heading)}")
    if len(sections) > 20:
        lines.append(f"    {len(sections[:20]) + 1}. 更多页面")
        lines.append(f"      共 {len(sections)} 页，详见正文")
    mindmap = "\n".join(lines)
```

注意：这里需要同时修复 `_safe_mermaid` 破坏 `root((...))` 语法的问题。修改 `_safe_mermaid` 为只处理节点文本，不处理根节点语法包装。

把：
```python
lines = ["mindmap", f"  root(({_safe_mermaid(title)}))"]
```

改为：
```python
root_text = title.replace(":", "：").strip() or "未命名"
lines = ["mindmap", f"  root(({root_text}))"]
```

并调整 `_safe_mermaid` 保持括号不变：

```python
def _safe_mermaid(text: str) -> str:
    return text.replace(":", "：").strip() or "未命名"
```

- [ ] **Step 3: 运行测试确认通过**

Run: `pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_document.py::test_generate_mindmap_adds_chapter_numbers -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/document.py \
        .agents/skills/video-to-slides/scripts/videotodoc/tests/test_document.py
git commit -m "fix(mindmap): add chapter numbers in fallback mindmap and keep root syntax valid"
```

---

### Task 4: 更新 CLI 移除 `--mermaid` 参数

**Files:**
- Modify: `.agents/skills/video-to-slides/scripts/videotodoc/cli.py:88-90,181-188`
- Test: `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_cli.py`

**Interfaces:**
- Consumes: `argparse`
- Produces: `render-mindmap` 子命令不再接受 `--mermaid`

- [ ] **Step 1: 修改 CLI 帮助文本和 `_render_mindmap`**

把：
```python
    mindmap = subparsers.add_parser("render-mindmap", help="渲染 mindmap.mmd 并刷新 Word")
    mindmap.add_argument("run_dir", type=Path)
    mindmap.add_argument("--mermaid", action="store_true", help="使用 Mermaid CLI 渲染（默认使用 Python 渲染器）")
```

改为：
```python
    mindmap = subparsers.add_parser("render-mindmap", help="渲染 mindmap.mmd 并刷新 Word")
    mindmap.add_argument("run_dir", type=Path)
```

把：
```python
def _render_mindmap(args: argparse.Namespace) -> int:
    image_paths, refreshed = render_mindmap_and_refresh_docs(args.run_dir, use_mermaid=args.mermaid)
```

改为：
```python
def _render_mindmap(args: argparse.Namespace) -> int:
    image_paths, refreshed = render_mindmap_and_refresh_docs(args.run_dir)
```

- [ ] **Step 2: 运行现有 CLI 测试**

Run: `pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_cli.py -v`
Expected: PASS（或根据测试代码调整）

- [ ] **Step 3: Commit**

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/cli.py \
        .agents/skills/video-to-slides/scripts/videotodoc/tests/test_cli.py
git commit -m "refactor(cli): remove --mermaid flag, tidy-tree is now the only renderer"
```

---

### Task 5: 清理 Python 渲染遗留代码和文件

**Files:**
- Delete: `.agents/skills/video-to-slides/scripts/videotodoc/mindmap_layout.py`
- Delete: `.agents/skills/video-to-slides/scripts/videotodoc/mindmap_verify.py`
- Delete: `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_layout.py`
- Delete: `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_verify.py`
- Delete: `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_edge_cases.py`
- Delete: `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_multi.py`
- Modify: `.agents/skills/video-to-slides/scripts/videotodoc/mindmap.py`（已在 Task 2 重写，确保没有残留导入）

- [ ] **Step 1: 删除上述文件**

```bash
rm .agents/skills/video-to-slides/scripts/videotodoc/mindmap_layout.py
rm .agents/skills/video-to-slides/scripts/videotodoc/mindmap_verify.py
rm .agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_layout.py
rm .agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_verify.py
rm .agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_edge_cases.py
rm .agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_multi.py
```

- [ ] **Step 2: 运行全量测试确认无残留依赖**

Run: `pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/ -v --tb=short`
Expected: PASS（mindmap 相关测试通过，其他测试不受影响）

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "chore(mindmap): remove Python renderer, layout engine, and obsolete tests"
```

---

### Task 6: 新增校验与拆图策略测试

**Files:**
- Create: `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_verification.py`

- [ ] **Step 1: 编写测试验证拆图避免稀疏子图**

```python
def test_split_avoids_sparse_last_image():
    from videotodoc.mindmap_mermaid import split_mmd_by_chapters

    text = """mindmap
  root((R))
    A
      a1
      a2
      a3
      a4
      a5
    B
      b1
"""
    parts = split_mmd_by_chapters(text, max_nodes=10, min_chapters=1, min_nodes=3)
    assert len(parts) == 1
    assert "1. A" in parts[0]
    assert "2. B" in parts[0]
```

- [ ] **Step 2: 编写测试验证 PNG 尺寸校验**

```python
from pathlib import Path
from unittest.mock import patch


def test_render_raises_on_oversized_png(tmp_path: Path):
    from videotodoc.mindmap import render_mindmap_and_refresh_docs

    mmd = tmp_path / "mindmap.mmd"
    mmd.write_text("mindmap\n  root((R))\n    A\n", encoding="utf-8")

    def fake_run_mmdc(args: list[str]) -> None:
        output_path = Path(args[args.index("-o") + 1])
        from PIL import Image
        img = Image.new("RGBA", (4000, 100), (255, 255, 255, 0))
        img.save(output_path)

    with patch("videotodoc.mindmap._run_mmdc", side_effect=fake_run_mmdc):
        from videotodoc.utils import VideoToDocError
        try:
            render_mindmap_and_refresh_docs(tmp_path)
            assert False, "应该抛出尺寸超限错误"
        except VideoToDocError as exc:
            assert "尺寸过大" in str(exc)
```

Run: `pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_verification.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_verification.py
git commit -m "test(mindmap): add verification tests for sparse split and oversized png"
```

---

### Task 7: 端到端验证

**Files:**
- 使用真实 run 目录：`.agents/skills/video-to-slides/scripts/videotodoc/tests/` 或 `runs/Git+Github核心概念串讲，从零到一全攻略_20260628_212556/`

- [ ] **Step 1: 找到最近一次 run 目录中的 `.mmd`**

Run:
```bash
ls -t runs/*/*.mmd | head -5
```

Expected: 输出最近的 `.mmd` 文件路径

- [ ] **Step 2: 手动运行 `render-mindmap` 命令**

Run:
```bash
python -m videotodoc render-mindmap <run_dir>
```

Expected: 成功生成 `mindmap_01.png`、`mindmap_02.png` 等文件

- [ ] **Step 3: 检查输出图片**

Run:
```bash
file <run_dir>/mindmap_01.png
file <run_dir>/mindmap_02.png
```

Expected: 输出 PNG 尺寸，宽度 ≤ 3000px，高度 ≤ 3000px

- [ ] **Step 4: 检查 Markdown 插入**

Run:
```bash
grep -n "思维导图" <run_dir>/*_讲义_整理版_*.md
```

Expected: Markdown 中 `## 思维导图` 章节包含所有子图的引用

- [ ] **Step 5: Commit（如有产物更新）**

如果端到端验证过程中修改了代码，提交修复。

---

### Task 8: 更新 SKILL.md 文档

**Files:**
- Modify: `.agents/skills/video-to-slides/SKILL.md`

- [ ] **Step 1: 找到 SKILL.md 中关于思维导图渲染的章节**

Run:
```bash
grep -n "思维导图\|mindmap\|mermaid" .agents/skills/video-to-slides/SKILL.md
```

- [ ] **Step 2: 更新描述为 tidy-tree**

将原有描述替换为：

```markdown
### 思维导图渲染

思维导图使用 Mermaid CLI (`mmdc`) 的 `tidy-tree` 布局渲染，不再使用 Python Pillow 手动绘制。

行为：
- 生成的 `.mmd` 自动注入 `layout: tidy-tree` 配置
- 1 级章节标题自动添加序号，如 `1. 基础概念`
- 当单图节点过多时，按章节拆分为 `mindmap_01.png`、`mindmap_02.png` 等多张图片
- 渲染后检查单图尺寸是否超过 3000×3000px
- Markdown 和 Word 会自动引用所有子图
```

- [ ] **Step 3: Commit**

```bash
git add .agents/skills/video-to-slides/SKILL.md
git commit -m "docs(mindmap): update SKILL.md to reflect tidy-tree renderer"
```

---

## 自我审查

1. **Spec coverage:**
   - tidy-tree 渲染 → Task 2
   - 章节序号 → Task 3
   - 按章节拆图 → Task 1
   - 尺寸校验 → Task 2, Task 6
   - 移除 Python 渲染 → Task 5
   - 移除视觉模型 → 不做什么 部分
   - Markdown/Word 多图引用 → Task 2（复用现有 ensure_mindmap_link）
   - 文档更新 → Task 8

2. **Placeholder scan:** 无 TBD、TODO 或未完成的代码块。

3. **Type consistency:** `render_mindmap_and_refresh_docs` 签名保持不变；`split_mmd_by_chapters` 返回 `list[str]`；`inject_tidy_tree_config` 等返回 `str`。

---

## 最终验收标准（用户确认版）

所有功能完成后，必须满足以下验收条件：

1. **连线不重叠、不交叉**
   - Mermaid `tidy-tree` 布局自动保证节点间连线不重叠、不交叉
   - 若发现明显交叉，视为渲染失败，需调整拆图策略或 Mermaid 配置

2. **文字不互相遮挡**
   - 节点文本完整显示，不出现 "…" 截断
   - 节点之间、文字之间无重叠
   - 通过 OCR/像素分析或人工抽查验证

3. **布局合理**
   - **少量章节**：采用纵向树状布局（单张图从上到下展开）
   - **分支增多**：自动拆成横向的多个数列（Mermaid tidy-tree 自动横向展开）
   - **节点过多**：按章节拆成多张 PNG（`mindmap_01.png`、`mindmap_02.png`…）

4. **1 级章节标题带序号**
   - 如 `1. 基础概念`、`2. 本地仓库核心`

5. **Markdown/Word 正确引用所有子图**
   - 每张拆分的子图都应在 `## 思维导图` 章节中列出
   - 多次运行不重复累积图片引用

6. **拆图避免稀疏子图**
   - 每张图至少包含 2 个章节或 10 个节点
   - 避免出现只含 1 章 4 个叶子节点的空泛子图

7. **单图尺寸可控**
   - 宽度 ≤ 3000px，高度 ≤ 3000px

8. **彻底移除 Python Pillow 渲染路径**
   - 删除 `mindmap_layout.py`、`mindmap_verify.py` 及相关测试
   - CLI 不再提供 `--mermaid` 参数（Mermaid 是唯一渲染后端）

9. **不调用视觉模型或云端多模态 API**
   - 校验仅使用本地脚本（尺寸、节点数、简单 OCR）
