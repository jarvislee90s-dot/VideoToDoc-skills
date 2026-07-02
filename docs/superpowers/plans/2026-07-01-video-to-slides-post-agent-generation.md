# video-to-slides 后置生成（Post-Agent Generation）实现计划

> **面向 Agent 工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 按任务逐项实现。步骤使用复选框（`- [ ]`）语法以便跟踪。

**目标：** 将思维导图（`.mmd`/`.png`）和 Word 文档（`.docx`）的生成从 `video-to-slides` 流水线中间移到 Agent 语义整理之后，消除基于占位符的预生成。

**架构：** 让 `ProcessResult` 仅反映中间 Markdown 输出；从 `pipeline.py` 中移除思维导图和 docx 生成；扩展 `render_mindmap.py` 的最后一步，使其同时渲染思维导图并生成/刷新紧凑版和整理版 Word 文档。

**技术栈：** Python 3.9+、`python-docx`、`Pillow`、`pytest`、Mermaid CLI（`mmdc`）。

## 全局约束

- 保持 Markdown 文件现有命名约定（`{slug}_讲义_*.md`）。
- 保留紧凑版 docx 命名约定：紧凑版 Markdown `{slug}_讲义_紧凑版_{ts}.md` 对应 `{slug}_讲义_{ts}.docx`。
- 保持向后兼容：`render_mindmap.py` 仍会刷新旧 run 目录中已存在的 `.docx` 文件。
- 不要删除 `generate_mindmap` 或 `markdown_to_docx`；它们继续供 LLM/自动模式或外部使用。
- 所有现有测试必须更新而非删除；新行为必须有测试覆盖。
- 流水线必须向 `render_compact_markdown` 和 `ensure_semantic_markdown` 传入 `mindmap_image_path=None`，确保 Markdown 文件不带思维导图占位符。

---

## 文件结构

| 文件 | 职责 |
|------|---------------|
| `.agents/skills/video-to-slides/scripts/videotodoc/models.py` | `ProcessResult` 数据类；将 `mindmap_path` 改为可选。 |
| `.agents/skills/video-to-slides/scripts/videotodoc/pipeline.py` | 流水线只生成中间 Markdown；移除思维导图/docx 生成。 |
| `.agents/skills/video-to-slides/scripts/videotodoc/mindmap.py` | `render_mindmap_and_refresh_docs` 渲染思维导图并生成/刷新 docx 文件。 |
| `.agents/skills/video-to-slides/scripts/render_mindmap.py` | CLI 包装脚本；更新描述/帮助文本。 |
| `.agents/skills/video-to-slides/scripts/videotodoc/cli.py` | CLI 输出处理可选的 `mindmap_path`。 |
| `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_document.py` | 添加 `ProcessResult` 可选字段测试。 |
| `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_doc_generation_parallel.py` | 更新断言：流水线后只存在 Markdown/质量报告。 |
| `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_pipeline_parallel.py` | 更新断言：流水线后只存在 Markdown/质量报告。 |
| `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_run_dir_title.py` | 将标题断言从 `mindmap_path` 移到 `markdown_path`。 |
| `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_render.py` | 添加测试：缺失 docx 时会被生成。 |
| `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_cli.py` | 添加测试：CLI 跳过打印缺失的可选字段。 |
| `.agents/skills/video-to-slides/README.md`（或包含工作流描述的技能定义文件） | 更新工作流描述：pipeline → Agent → render_mindmap。 |

---

### 任务 1：将 `ProcessResult.mindmap_path` 改为可选

**文件：**
- 修改：`.agents/skills/video-to-slides/scripts/videotodoc/models.py:74-87`
- 测试：`.agents/skills/video-to-slides/scripts/videotodoc/tests/test_document.py`

**接口：**
- 消费：`ProcessResult` 构造函数的调用方。
- 产出：`ProcessResult`，其中 `mindmap_path: Path | None = None`。

- [ ] **步骤 1：编写失败测试**

追加到 `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_document.py`：

```python
def test_process_result_mindmap_path_optional(tmp_path: Path):
    from videotodoc.models import ProcessResult
    result = ProcessResult(
        run_dir=tmp_path,
        transcript_path=tmp_path / "t.json",
        slides_path=tmp_path / "s.json",
        sections_path=tmp_path / "a.json",
        markdown_path=tmp_path / "m.md",
        mindmap_path=None,
    )
    assert result.mindmap_path is None
```

- [ ] **步骤 2：运行测试确认失败**

运行：
```bash
cd /Users/jarvis/Documents/VideoToDoc-skills/.agents/skills/video-to-slides/scripts
PYTHONPATH=/Users/jarvis/Documents/VideoToDoc-skills/.agents/skills/video-to-slides/scripts \
  pytest videotodoc/tests/test_document.py::test_process_result_mindmap_path_optional -v
```

预期：失败，提示 `TypeError: non-default argument 'mindmap_path' follows default argument` 或 `missing 1 required positional argument`。

- [ ] **步骤 3：编写最小实现**

在 `.agents/skills/video-to-slides/scripts/videotodoc/models.py` 中，将 `ProcessResult` 改为：

```python
@dataclass
class ProcessResult:
    run_dir: Path
    transcript_path: Path
    slides_path: Path
    sections_path: Path
    markdown_path: Path
    mindmap_path: Path | None = None
    compact_markdown_path: Path | None = None
    semantic_markdown_path: Path | None = None
    mindmap_image_path: Path | None = None
    mindmap_image_paths: list[Path] = field(default_factory=list)
    docx_path: Path | None = None
    semantic_docx_path: Path | None = None
    quality_report_path: Path | None = None
```

- [ ] **步骤 4：运行测试确认通过**

运行同样的 pytest 命令。

预期：通过。

- [ ] **步骤 5：提交**

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/models.py
```

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/tests/test_document.py
git commit -m "feat: make ProcessResult.mindmap_path optional"
```

---

### 任务 2：从 `pipeline.py` 中移除思维导图和 docx 生成，并统一视频标题来源

**文件：**
- 修改：`.agents/skills/video-to-slides/scripts/videotodoc/pipeline.py:286-346` 和 `:462-537`
- 测试：`.agents/skills/video-to-slides/scripts/videotodoc/tests/test_doc_generation_parallel.py`、`.agents/skills/video-to-slides/scripts/videotodoc/tests/test_pipeline_parallel.py`

**接口：**
- 消费：任务 1 的 `ProcessResult`。
- 产出：`ProcessResult`，其中 `mindmap_path=None`、`mindmap_image_path=None`、`docx_path=None`、`semantic_docx_path=None`；Markdown 文件名和内部标题均使用统一的视频标题（来自 run_dir 名称去掉时间戳）。

- [ ] **步骤 1：编写失败测试更新**

在 `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_doc_generation_parallel.py` 中，将最后的断言块（第 138-144 行）替换为：

```python
        assert result.markdown_path.exists(), "原始 markdown 应生成"
        assert result.compact_markdown_path.exists(), "紧凑版 markdown 应生成"
        assert result.semantic_markdown_path.exists(), "整理版 markdown 应生成"
        assert result.mindmap_path is None, "pipeline 不应生成思维导图 mmd"
        assert result.mindmap_image_path is None, "pipeline 不应生成思维导图 PNG"
        assert result.docx_path is None, "pipeline 不应生成 docx"
        assert result.semantic_docx_path is None, "pipeline 不应生成整理版 docx"
        assert result.quality_report_path.exists(), "质量报告应生成"
```

同时从此文件的 `with patch(...)` 块中移除不再使用的 `generate_mindmap`、`render_mindmap_and_refresh_docs`、`markdown_to_docx` mock。

在 `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_pipeline_parallel.py` 中，在第 191 行后添加：

```python
        assert result.compact_markdown_path.exists()
        assert result.semantic_markdown_path.exists()
        assert result.mindmap_path is None
        assert result.docx_path is None
        assert result.semantic_docx_path is None
```

同时从此文件的 `with patch(...)` 块中移除不再使用的 `generate_mindmap`、`render_mindmap_and_refresh_docs`、`markdown_to_docx` mock。

- [ ] **步骤 2：运行测试确认失败**

运行：
```bash
PYTHONPATH=/Users/jarvis/Documents/VideoToDoc-skills/.agents/skills/video-to-slides/scripts \
  pytest videotodoc/tests/test_doc_generation_parallel.py videotodoc/tests/test_pipeline_parallel.py -v
```

预期：失败，因为流水线仍会生成思维导图/docx，而测试已预期它们不存在。

- [ ] **步骤 3：修改 `finalize_video`**

在 `.agents/skills/video-to-slides/scripts/videotodoc/pipeline.py` 中，将第 286-346 行替换为：

```python
    # 生成产物（仅 Markdown，思维导图与 Word 在 Agent 整理后由 render_mindmap.py 生成）
    slug = confirmed.get("video_title", run_dir.stem)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    markdown_path = run_dir / f"{slug}_讲义_{ts}.md"
    compact_markdown_path = run_dir / f"{slug}_讲义_紧凑版_{ts}.md"
    semantic_markdown_path = run_dir / f"{slug}_讲义_整理版_{ts}.md"

    def _render_original_md():
        render_original_markdown(slug, sections, markdown_path)

    with ThreadPoolExecutor(max_workers=1) as executor:
        f_orig_md = executor.submit(_render_original_md)
        f_orig_md.result()

    def _render_compact_md():
        render_compact_markdown(slug, sections, compact_markdown_path, mindmap_image_path=None)

    def _render_semantic_md():
        ensure_semantic_markdown(slug, sections, semantic_markdown_path, mindmap_image_path=None)

    with ThreadPoolExecutor(max_workers=2) as executor:
        f_compact = executor.submit(_render_compact_md)
        f_semantic = executor.submit(_render_semantic_md)
        f_compact.result()
        f_semantic.result()

    return {
        "run_dir": str(run_dir.resolve()),
        "selected_slides_count": len(flat_slides),
    }
```

- [ ] **步骤 4：修改 `process_video`**

在 `.agents/skills/video-to-slides/scripts/videotodoc/pipeline.py` 中，将第 391-537 行替换为：

```python
    # 产物命名：仅 Markdown，思维导图与 Word 在 Agent 整理后生成
    markdown_path = run_dir / f"{slug}_讲义_{ts}.md"
    compact_markdown_path = run_dir / f"{slug}_讲义_紧凑版_{ts}.md"
    semantic_markdown_path = run_dir / f"{slug}_讲义_整理版_{ts}.md"
    quality_report_path = run_dir / f"{slug}_质量报告_{ts}.md"

    # 步骤 1：提取音频
    audio = extract_audio(video_path, audio_path, settings, force=_stage_forced(force_rebuild, "audio"))

    # 步骤 2-3 并行：ASR 转录 + 候选截图检测
    if settings.transcript_path:
        tpath = Path(settings.transcript_path)
        merged_path = tpath.parent / "transcript_merged.json"
        source_path = merged_path if merged_path.exists() else tpath
        if merged_path.exists():
            print(f"  ♻️  使用已合并转录：{merged_path.name}")
        transcript = _transcript_from_external(read_json(source_path), settings.language)
        print(f"  ♻️  转录段数：{len(transcript.segments)}")
        candidates = detect_slides(
            video_path, slides_dir, slides_path, settings,
            force=_stage_forced(force_rebuild, "slides"),
            skip_dedupe=True,
        )
    else:
        def _run_asr_pv():
            return transcribe_audio(audio, transcript_path, settings, force=_stage_forced(force_rebuild, "asr"))
        def _run_detect_pv():
            return detect_slides(
                video_path, slides_dir, slides_path, settings,
                force=_stage_forced(force_rebuild, "slides"),
                skip_dedupe=True,
            )
        with ThreadPoolExecutor(max_workers=2) as executor:
            f_asr_pv = executor.submit(_run_asr_pv)
            f_detect_pv = executor.submit(_run_detect_pv)
            transcript = f_asr_pv.result()
            candidates = f_detect_pv.result()

    # 步骤 4：按 ASR 段裁剪候选图（同段多图只留最后一张）
    trimmed = trim_candidates_by_transcript(
        candidates, transcript, video_path, trimmed_dir, settings,
    )

    # 步骤 5：跨段图像/OCR 去重
    slides = deduplicate_slides(trimmed, settings)

    # 步骤 6：把入选截图复制到干净目录
    candidates_metadata = candidates.metadata  # 保留候选阶段元数据
    slides = materialize_selected_slides(slides, selected_slides_dir)
    slides.metadata["candidates_metadata"] = candidates_metadata
    write_json(slides_path, to_plain_dict(slides))

    # 步骤 7：图文对齐
    if sections_path.exists() and not _stage_forced(force_rebuild, "align"):
        sections_data = read_json(sections_path)
        sections = sections_from_dict(sections_data)
        sync_offset_ms = int(sections_data.get("sync_offset_ms", 0))
    else:
        sync_offset_ms = estimate_sync_offset_ms(audio, slides, transcript, settings)
        sections = align_sections(slides, transcript, sync_offset_ms)
        write_json(
            sections_path,
            {
                "sync_offset_ms": sync_offset_ms,
                "sections": [to_plain_dict(section) for section in sections],
            },
        )

    def _render_original_md_pv():
        # 统一使用 slug（来自 run_dir 标题），避免 video_path.stem 导致标题变成 "video"
        render_original_markdown(slug, sections, markdown_path)

    def _write_quality_report_pv():
        write_quality_report(quality_report_path, transcript, slides, sections, sync_offset_ms)

    with ThreadPoolExecutor(max_workers=2) as executor:
        f_orig_md_pv = executor.submit(_render_original_md_pv)
        f_quality_pv = executor.submit(_write_quality_report_pv)
        f_orig_md_pv.result()
        f_quality_pv.result()

    def _render_compact_md_pv():
        render_compact_markdown(
            slug,
            sections,
            compact_markdown_path,
            mindmap_image_path=None,
        )

    def _render_semantic_md_pv():
        ensure_semantic_markdown(
            slug,
            sections,
            semantic_markdown_path,
            mindmap_image_path=None,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        f_compact_pv = executor.submit(_render_compact_md_pv)
        f_semantic_pv = executor.submit(_render_semantic_md_pv)
        f_compact_pv.result()
        f_semantic_pv.result()

    return ProcessResult(
        run_dir=run_dir,
        transcript_path=transcript_path,
        slides_path=slides_path,
        sections_path=sections_path,
        markdown_path=markdown_path,
        mindmap_path=None,
        compact_markdown_path=compact_markdown_path,
        semantic_markdown_path=semantic_markdown_path,
        mindmap_image_path=None,
        mindmap_image_paths=[],
        docx_path=None,
        semantic_docx_path=None,
        quality_report_path=quality_report_path,
    )
```

- [ ] **步骤 5：移除未使用的导入**

修改后，检查 `pipeline.py` 顶部的导入。`generate_mindmap`、`render_mindmap_and_refresh_docs`、`markdown_to_docx` 在流水线中不再被引用，应全部移除。

预期的 `.document` 最终导入：
```python
from .document import (
    ensure_semantic_markdown,
    render_compact_markdown,
    render_original_markdown,
)
```

同时移除 `from .mindmap import render_mindmap_and_refresh_docs`。

- [ ] **步骤 6：运行测试确认通过**

运行：
```bash
PYTHONPATH=/Users/jarvis/Documents/VideoToDoc-skills/.agents/skills/video-to-slides/scripts \
  pytest videotodoc/tests/test_doc_generation_parallel.py videotodoc/tests/test_pipeline_parallel.py videotodoc/tests/test_run_dir_title.py -v
```

预期：通过。

- [ ] **步骤 7：提交**

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/pipeline.py
```

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/tests/test_doc_generation_parallel.py
git add .agents/skills/video-to-slides/scripts/videotodoc/tests/test_pipeline_parallel.py
git commit -m "refactor: pipeline generates only intermediate markdowns and uses consistent video title"
```

---

### 任务 3：更新 `render_mindmap_and_refresh_docs`，在 docx 缺失时生成它

**文件：**
- 修改：`.agents/skills/video-to-slides/scripts/videotodoc/mindmap.py:14-52`
- 测试：`.agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_render.py`

**接口：**
- 消费：包含 `mindmap.mmd`、紧凑版 Markdown、整理版 Markdown 的 `run_dir`。
- 产出：`mindmap.png`、带思维导图链接的刷新后 Markdown、紧凑版/整理版 `.docx`。

- [ ] **步骤 1：编写失败测试**

追加到 `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_render.py`：

```python
def test_render_generates_missing_docx_for_compact_and_semantic(tmp_path: Path):
    from videotodoc.mindmap import render_mindmap_and_refresh_docs

    mmd = tmp_path / "mindmap.mmd"
    mmd.write_text("mindmap\n  root((R))\n    A\n      a1\n", encoding="utf-8")

    compact_md = tmp_path / "视频_讲义_紧凑版_20260101_120000.md"
    compact_md.write_text("# 紧凑\n\n## 图文讲义\n", encoding="utf-8")
    semantic_md = tmp_path / "视频_讲义_整理版_20260101_120000.md"
    semantic_md.write_text("# 整理\n\n## 图文讲义\n", encoding="utf-8")
    original_md = tmp_path / "视频_讲义_20260101_120000.md"
    original_md.write_text("# 原始\n", encoding="utf-8")

    generated_docxes: list[Path] = []

    def fake_markdown_to_docx(md_path: Path, docx_path: Path) -> Path:
        docx_path.write_bytes(b"fake docx")
        generated_docxes.append(docx_path)
        return docx_path

    with patch("videotodoc.mindmap._run_mmdc", side_effect=_fake_mmdc_runner), \
         patch("videotodoc.mindmap.markdown_to_docx", side_effect=fake_markdown_to_docx):
        image_paths, refreshed = render_mindmap_and_refresh_docs(tmp_path)

    assert len(image_paths) == 1
    assert len(refreshed) == 2
    assert any("视频_讲义_20260101_120000.docx" == p.name for p in refreshed)
    assert any("视频_讲义_整理版_20260101_120000.docx" == p.name for p in refreshed)
    assert not any("视频_讲义_紧凑版_" in p.name for p in refreshed)
```

- [ ] **步骤 2：运行测试确认失败**

运行：
```bash
PYTHONPATH=/Users/jarvis/Documents/VideoToDoc-skills/.agents/skills/video-to-slides/scripts \
  pytest videotodoc/tests/test_mindmap_render.py::test_render_generates_missing_docx_for_compact_and_semantic -v
```

预期：失败，因为当前代码只在 docx 已存在时刷新。

- [ ] **步骤 3：编写最小实现**

在 `.agents/skills/video-to-slides/scripts/videotodoc/mindmap.py` 中，将 `render_mindmap_and_refresh_docs` 的文档字符串和循环替换为：

```python
def render_mindmap_and_refresh_docs(
    run_dir: Path,
    mindmap_path: Path | None = None,
    image_path: Path | None = None,
    use_mermaid: bool = False,
) -> tuple[list[Path], list[Path]]:
    """使用 Mermaid tidy-tree 渲染思维导图，并生成/刷新所有 Markdown/Word 文档。"""
    del use_mermaid  # 已废弃，保留参数兼容性

    run_dir = run_dir.resolve()
    mindmap_path = mindmap_path or (run_dir / "mindmap.mmd")
    image_path = image_path or (run_dir / "mindmap.png")
    if not mindmap_path.exists():
        raise VideoToDocError(
            f"找不到 Mermaid 源文件：{mindmap_path}。"
            "请先完成 Agent 整理步骤并编写 mindmap.mmd，再运行此脚本。"
        )

    raw_text = mindmap_path.read_text(encoding="utf-8")
    numbered = add_chapter_numbers(raw_text)
    prepared = inject_tidy_tree_config(numbered)

    prepared_path = run_dir / "mindmap_prepared.mmd"
    prepared_path.write_text(prepared, encoding="utf-8")

    mmdc = _find_mmdc()
    _run_mmdc([mmdc, "-i", str(prepared_path), "-o", str(image_path), "-b", "transparent", "-w", "2400"])
    _verify_png_size(image_path)

    image_paths = [image_path]

    refreshed: list[Path] = []
    for md_file in run_dir.glob("*.md"):
        if "质量报告" in md_file.name:
            continue
        ensure_mindmap_link(md_file, image_paths)
        docx_file = _docx_path_for_markdown(md_file)
        generated = markdown_to_docx(md_file, docx_file)
        if generated:
            refreshed.append(generated)
    return image_paths, refreshed


def _docx_path_for_markdown(md_path: Path) -> Path:
    """保持旧命名约定：紧凑版 Markdown 对应 _讲义_.docx，整理版保持同名。"""
    name = md_path.stem
    if "_讲义_紧凑版_" in name:
        slug, ts = name.split("_讲义_紧凑版_", 1)
        return md_path.with_name(f"{slug}_讲义_{ts}.docx")
    return md_path.with_suffix(".docx")
```

- [ ] **步骤 4：运行测试确认通过**

运行：
```bash
PYTHONPATH=/Users/jarvis/Documents/VideoToDoc-skills/.agents/skills/video-to-slides/scripts \
  pytest videotodoc/tests/test_mindmap_render.py -v
```

预期：通过。

- [ ] **步骤 5：提交**

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/mindmap.py
```

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_render.py
git commit -m "feat: render_mindmap generates missing docx and refreshes existing ones"
```

---

### 任务 4：更新 `render_mindmap.py` CLI 描述

**文件：**
- 修改：`.agents/skills/video-to-slides/scripts/render_mindmap.py:1-3, 15-17, 25-26`

**接口：**
- 消费：包含 `mindmap.mmd` 的 `run_dir`。
- 产出：渲染后的思维导图 PNG 和 Word 文档。

- [ ] **步骤 1：修改脚本**

在 `.agents/skills/video-to-slides/scripts/render_mindmap.py` 中：

第 2 行：
```python
"""渲染 run 目录中的 mindmap.mmd，并生成/刷新两份 Word 产物。"""
```

第 16 行：
```python
    parser = argparse.ArgumentParser(description="渲染思维导图并生成/刷新 Word 产物。")
```

第 25-26 行：
```python
    if run_dir is None:
        print("未找到包含 mindmap.mmd 的 run 目录。请确认 Agent 已编写 mindmap.mmd。")
        return 2
```

- [ ] **步骤 2：验证帮助文本**

运行：
```bash
python3 .agents/skills/video-to-slides/scripts/render_mindmap.py --help
```

预期输出包含 "渲染思维导图并生成/刷新 Word 产物"。

- [ ] **步骤 3：提交**

```bash
git add .agents/skills/video-to-slides/scripts/render_mindmap.py
git commit -m "docs: update render_mindmap CLI description for post-agent generation"
```

---

### 任务 5：更新 `cli.py` 以处理可选的 `mindmap_path`

**文件：**
- 修改：`.agents/skills/video-to-slides/scripts/videotodoc/cli.py:154-177`
- 测试：`.agents/skills/video-to-slides/scripts/videotodoc/tests/test_cli.py`

**接口：**
- 消费：`ProcessResult`，其中 `mindmap_path` 为可选。
- 产出：跳过缺失字段的 CLI 输出。

- [ ] **步骤 1：编写失败测试**

创建或追加到 `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_cli.py`：

```python
from pathlib import Path
from unittest.mock import MagicMock, patch

from videotodoc.cli import _process
from videotodoc.models import ProcessResult


def test_process_output_skips_missing_optional_fields(tmp_path: Path, capsys):
    result = ProcessResult(
        run_dir=tmp_path,
        transcript_path=tmp_path / "t.json",
        slides_path=tmp_path / "s.json",
        sections_path=tmp_path / "a.json",
        markdown_path=tmp_path / "m.md",
        mindmap_path=None,
        compact_markdown_path=tmp_path / "c.md",
        semantic_markdown_path=tmp_path / "z.md",
        mindmap_image_path=None,
        mindmap_image_paths=[],
        docx_path=None,
        semantic_docx_path=None,
        quality_report_path=tmp_path / "q.md",
    )
    args = MagicMock()
    args.video = tmp_path / "video.mp4"
    args.runs_dir = tmp_path / "runs"
    args.run_dir = None
    args.force_rebuild = []
    args.config = None

    settings = MagicMock()
    settings.transcript_path = None

    with patch("videotodoc.cli._settings_from_args", return_value=settings):
        with patch("videotodoc.cli.process_video", return_value=result):
            rc = _process(args)

    captured = capsys.readouterr()
    assert rc == 0
    assert "- mindmap:" not in captured.out
    assert "- mindmap_image:" not in captured.out
    assert "- docx:" not in captured.out
    assert "- semantic_docx:" not in captured.out
    assert "- compact_markdown:" in captured.out
    assert "- semantic_markdown:" in captured.out
```

- [ ] **步骤 2：运行测试确认失败**

运行：
```bash
PYTHONPATH=/Users/jarvis/Documents/VideoToDoc-skills/.agents/skills/video-to-slides/scripts \
  pytest videotodoc/tests/test_cli.py::test_process_output_skips_missing_optional_fields -v
```

预期：失败，提示在打印 `result.mindmap_path` 时出现 `TypeError` 或 `AttributeError`。

- [ ] **步骤 3：修改输出块**

在 `.agents/skills/video-to-slides/scripts/videotodoc/cli.py` 中，将 `_process` 的输出块（第 154-177 行）替换为：

```python
def _process(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    result = process_video(args.video, args.runs_dir, settings, set(args.force_rebuild),
                              run_dir=args.run_dir)
    print("处理完成：")
    print(f"- run_dir: {result.run_dir}")
    print(f"- transcript: {result.transcript_path}")
    print(f"- slides: {result.slides_path}")
    print(f"- sections: {result.sections_path}")
    print(f"- markdown: {result.markdown_path}")
    if result.compact_markdown_path:
        print(f"- compact_markdown: {result.compact_markdown_path}")
    if result.semantic_markdown_path:
        print(f"- semantic_markdown: {result.semantic_markdown_path}")
    if result.mindmap_path:
        print(f"- mindmap: {result.mindmap_path}")
    if result.mindmap_image_path:
        print(f"- mindmap_image: {result.mindmap_image_path}")
    if result.docx_path:
        print(f"- docx: {result.docx_path}")
    if result.semantic_docx_path:
        print(f"- semantic_docx: {result.semantic_docx_path}")
    if result.quality_report_path:
        print(f"- quality_report: {result.quality_report_path}")
    return 0
```

- [ ] **步骤 4：运行测试确认通过**

运行：
```bash
PYTHONPATH=/Users/jarvis/Documents/VideoToDoc-skills/.agents/skills/video-to-slides/scripts \
  pytest videotodoc/tests/test_cli.py -v
```

预期：通过。

- [ ] **步骤 5：提交**

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/cli.py
```

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/tests/test_cli.py
git commit -m "fix: cli skips printing optional mindmap/docx fields when None"
```

---

### 任务 6：更新 `test_run_dir_title.py`

**文件：**
- 修改：`.agents/skills/video-to-slides/scripts/videotodoc/tests/test_run_dir_title.py:60-63`

**接口：**
- 消费：`ProcessResult`，其中 `mindmap_path=None`。
- 产出：标题断言移到 Markdown 路径上。

- [ ] **步骤 1：修改断言**

替换第 60-63 行：

```python
    assert "我的测试视频" in result.markdown_path.name
    assert "video_讲义" not in result.markdown_path.name
    assert "我的测试视频" in result.semantic_markdown_path.name
    # mindmap_path 不再由 pipeline 生成，无需断言
```

- [ ] **步骤 2：运行测试**

```bash
PYTHONPATH=/Users/jarvis/Documents/VideoToDoc-skills/.agents/skills/video-to-slides/scripts \
  pytest videotodoc/tests/test_run_dir_title.py -v
```

预期：通过。

- [ ] **步骤 3：提交**

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/tests/test_run_dir_title.py
git commit -m "test: remove mindmap_path assertion from run_dir title test"
```

---

### 任务 7：更新技能文档

**文件：**
- 修改：`.agents/skills/video-to-slides/README.md`（或包含工作流描述的技能定义文件）

**接口：**
- 消费：新的工作流顺序。
- 产出：面向用户和 Agent 的更新后文档。

- [ ] **步骤 1：定位工作流章节**

搜索 "工作流总览" 或 "阶段 3：脚本自动收尾" 章节。

- [ ] **步骤 2：更新工作流概览**

将：

```markdown
## 工作流总览（三步中断式）

capture → review-segments(agent 介入) → finalize
```

改为：

```markdown
## 工作流总览（三步中断式）

capture → review-segments(agent 介入) → finalize（仅 Markdown） → render_mindmap（导图 + Word）
```

- [ ] **步骤 3：更新阶段说明**

在描述第一阶段（脚本自动阶段）的章节中，将输出列表改为说明 `.docx`/`.png` 尚未生成。

在 Agent 阶段或第三阶段下新增小节：

```markdown
### ⑩ 生成最终导图与 Word

在 Agent 完成目录插入、语义整理、手写 `mindmap.mmd` 之后，运行：

```bash
python3 .agents/skills/video-to-slides/scripts/restore_images.py \
  "runs/<视频标题>_<时间戳>/<视频标题>_讲义_紧凑版_<时间戳>.md" \
  "runs/<视频标题>_<时间戳>/<视频标题>_讲义_整理版_<时间戳>.md"

python3 .agents/skills/video-to-slides/scripts/render_mindmap.py \
  "runs/<视频标题>_<时间戳>"
```

`render_mindmap.py` 会一次性渲染思维导图并生成/刷新紧凑版、整理版两份 Word。
```

- [ ] **步骤 4：验证文档渲染**

打开 markdown 文件，确认各章节一致。

- [ ] **步骤 5：提交**

```bash
git add .agents/skills/video-to-slides/README.md
git commit -m "docs: update workflow for post-agent mindmap and docx generation"
```

---

### 任务 8：运行完整测试套件

**文件：**
- 测试：`.agents/skills/video-to-slides/scripts/videotodoc/tests/`

**接口：**
- 消费：任务 1-7 的所有改动。
- 产出：测试套件全部通过。

- [ ] **步骤 1：运行全部测试**

```bash
cd /Users/jarvis/Documents/VideoToDoc-skills/.agents/skills/video-to-slides/scripts
PYTHONPATH=/Users/jarvis/Documents/VideoToDoc-skills/.agents/skills/video-to-slides/scripts \
  pytest videotodoc/tests/ -v
```

预期：通过（排除与本改动无关的既有 Python 3.9 兼容性问题）。

- [ ] **步骤 2：提交剩余测试/文档改动**

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/tests/
git add docs/superpowers/plans/2026-07-01-video-to-slides-post-agent-generation.md
git commit -m "chore: finalize post-agent generation plan and test suite"
```

---

### 任务 9：端到端验收测试（使用 BV1A7V36BEc9）

**文件：**
- 视频：`https://www.bilibili.com/video/BV1A7V36BEc9/?spm_id_from=333.337.search-card.all.click`
- 产物：`runs/` 下新生成的 run 目录

**接口：**
- 消费：前面 8 个任务的代码改动。
- 产出：通过 `video-summary` → `video-to-slides` → Agent 整理 → `render_mindmap.py` → `feishu-markdown-publish` 的完整流程产物。

- [ ] **步骤 1：执行 video-summary**

运行 `video-summary` skill 处理视频 URL，得到转录和 run 目录。

- [ ] **步骤 2：执行 video-to-slides**

运行 `video-to-slides` skill，复用 `video-summary` 的 run 目录。

确认产物目录结构为单一 run 目录，例如：
```
runs/<视频标题>_<时间戳>/
├── cache/
├── selected_slides_finalized/
├── <视频标题>_讲义_<时间戳>.md
├── <视频标题>_讲义_紧凑版_<时间戳>.md
├── <视频标题>_讲义_整理版_<时间戳>.md
└── <视频标题>_质量报告_<时间戳>.md
```

- [ ] **步骤 3：Agent 整理并修复目录/思维导图**

由 Agent 完成：
1. 为整理版 Markdown 补全目录（二级标题结构）。
2. 根据整理版目录编写 `mindmap.mmd`，确保一级节点数量与整理版目录章节数一致，且每个一级节点标题与目录对应（包含章节编号）。

- [ ] **步骤 4：运行 render_mindmap.py**

```bash
python3 .agents/skills/video-to-slides/scripts/restore_images.py \
  "runs/<视频标题>_<时间戳>/<视频标题>_讲义_紧凑版_<时间戳>.md" \
  "runs/<视频标题>_<时间戳>/<视频标题>_讲义_整理版_<时间戳>.md"

python3 .agents/skills/video-to-slides/scripts/render_mindmap.py \
  "runs/<视频标题>_<时间戳>"
```

确认生成：
- `mindmap.png`
- `<视频标题>_讲义_<时间戳>.docx`
- `<视频标题>_讲义_整理版_<时间戳>.docx`

- [ ] **步骤 5：验收检查**

逐项验证：

1. **单一文件夹**：`runs/` 下只有一个以该视频标题命名的 run 目录，所有产物都在其中。
2. **产物文件名使用视频标题**：三个 Markdown 文件名均以视频标题开头，而非 `video.mp4` 等原始文件名。
3. **Markdown 内部标题使用视频标题**：打开原始版/紧凑版/整理版 Markdown，第一行 `# 标题` 为视频标题。
4. **整理版有目录**：打开整理版 Markdown/Word，开头存在目录，目录项为二级及以上标题。
5. **整理版目录与正文一致**：目录中的每一项都能在正文找到对应二级标题，数量、顺序、文字均一致。
6. **整理版 Word 图片为真实截图**：打开整理版 `.docx`，所有图片均为真实视频截图，没有 `[图片占位符]` 文本或空白占位框。
7. **思维导图一级节点带章节编号**：打开 `mindmap.png`，一级节点格式为 `1. xxx`、`2. xxx` 等。
8. **思维导图一级节点数量等于目录章节数**：一级节点数量与整理版目录章节数相同。
9. **思维导图一级节点语义与目录对应**：每个一级节点标题与整理版目录章节标题语义一致（允许缩写，但不允许错位或无关）。
10. **紧凑版 docx 命名正确**：紧凑版 Markdown 对应的 Word 文件名为 `<视频标题>_讲义_<时间戳>.docx`，不含 `_讲义_紧凑版_`。
11. **整理版 docx 与 Markdown 同名**：整理版 Word 文件名与整理版 Markdown 文件名一一对应。
12. **render_mindmap.py 生成前后状态正确**：运行前 run 目录中不存在 `mindmap.png` 和 `.docx`；运行后这两个产物正确生成。

- [ ] **步骤 6：执行 feishu-markdown-publish**

运行 `feishu-markdown-publish` skill，发布整理版 Markdown 到飞书云文档。

- [ ] **步骤 7：提交验收记录（可选）**

将端到端测试结果记录到计划文件末尾或单独验收文档：

```markdown
## 验收记录

- 视频：BV1A7V36BEc9
- 单一文件夹：是/否
- 产物文件名使用视频标题：是/否
- Markdown 内部标题使用视频标题：是/否
- 整理版目录：有/无
- 整理版目录与正文一致：是/否
- 整理版 Word 图片为真实截图：是/否
- 思维导图一级节点带章节编号：是/否
- 思维导图一级节点数量等于目录章节数：是/否
- 思维导图一级节点语义与目录对应：是/否
- 紧凑版 docx 命名正确：是/否
- 整理版 docx 与 Markdown 同名：是/否
- render_mindmap.py 生成前后状态正确：是/否
- 飞书文档链接：<链接>
```

---

## 自查

### 1. 规格覆盖

| 已批准计划中的需求 | 对应任务 |
|---|---|
| 流水线只生成中间 Markdown | 任务 2 |
| 思维导图/Word 在 Agent 整理后生成 | 任务 3、4 |
| 整理版 docx 包含真实图片，不含占位符 | 任务 3（在 `restore_images.py` 之后运行） |
| 保持现有文件名约定 | 任务 3（`_docx_path_for_markdown`） |
| 旧 run 目录向后兼容 | 任务 3（始终刷新已有 docx） |
| 更新测试 | 任务 1、2、5、6、8 |
| 更新技能文档 | 任务 7 |
| 单一 run 文件夹 | 任务 9 步骤 2 |
| 整理版含目录 | 任务 9 步骤 3 |
| 思维导图与整理版目录一致 | 任务 9 步骤 5 |

无遗漏。

### 2. 占位符检查

无 "TBD"、"TODO"、"implement later" 或模糊的 "add error handling" 步骤。每个步骤都包含精确文件路径、代码或命令。

### 3. 类型一致性

- `ProcessResult.mindmap_path` 在任务 1 中为 `Path | None`，在任务 2 中设为 `None`。
- `render_mindmap_and_refresh_docs` 返回类型保持 `tuple[list[Path], list[Path]]`。
- `_docx_path_for_markdown` 接收 `Path` 并返回 `Path`。
- `render_compact_markdown` 和 `ensure_semantic_markdown` 接受 `mindmap_image_path: Path | list[Path] | None`。

所有签名一致。

---

## 执行交接

计划已完成并保存到 `docs/superpowers/plans/2026-07-01-video-to-slides-post-agent-generation.md`。

两种执行方式：

**1. Subagent-Driven（推荐）**——我为每个任务派一个独立 subagent，任务间审查，快速迭代。

**2. Inline Execution**——在当前会话中使用 executing-plans skill 批量执行，关键节点设置检查点。

选择哪种方式？
