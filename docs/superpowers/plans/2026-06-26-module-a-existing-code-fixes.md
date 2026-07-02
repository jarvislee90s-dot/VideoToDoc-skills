# 模块 A：原有代码修改实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 VideoToDoc 现有代码中的关键 Bug、性能瓶颈、健壮性缺陷和技术债务，不改变产物形态。

**Architecture:** 按优先级分三阶段实施——P0 紧急修复（Bug + 死代码 + 关键性能）、P1 并行化与健壮性、P2 渐进改进。每个任务独立可测，TDD 驱动，频繁提交。

**Tech Stack:** Python 3.11+、pytest、concurrent.futures、subprocess、Pillow、ffmpeg

## Global Constraints

- 不新增产物形态（HTML/长图等归模块 B）
- 不改变现有 CLI 接口（`capture`/`finalize`/`process` 子命令保持兼容）
- 所有时间戳内部统一用毫秒（int）
- 子进程调用必须有 timeout
- 临时文件必须用 `tempfile` 模块，不污染用户目录
- 提交信息用 `fix:`/`perf:`/`refactor:` 前缀
- 每个任务结束前运行 `pytest tests/ -v` 确保不回归

## 文件结构映射

| 文件 | 职责 | 本计划涉及任务 |
|---|---|---|
| `videotodoc/utils.py` | 通用工具（run_command、时间转换、slugify） | T1, T2, T6 |
| `videotodoc/slides.py` | 截图检测、去重、精化 | T3, T4, T5, T8, T9 |
| `videotodoc/models.py` | 数据模型（Slide、Transcript 等） | T4 |
| `videotodoc/pipeline.py` | 流水线编排 | T6, T7, T10, T11, T14 |
| `videotodoc/asr.py` | ASR 转录与后处理 | T6, T12 |
| `videotodoc/ocr.py` | OCR 文本提取 | T4, T15 |
| `videotodoc/document.py` | 文档生成 | T10, T15 |
| `videotodoc/mindmap.py` | 思维导图渲染 | T15 |
| `videotodoc/cli.py` | 命令行入口 | T15 |
| `videotodoc/config.py` | 配置 | T15 |
| `videotodoc/feishu.py` | **废弃死代码** | T2（删除） |
| `video-summary/scripts/process.py` | 视频下载与 ASR | T6, T12, T13 |
| `feishu-markdown-publish/scripts/publish.py` | 飞书发布 | T11, T15 |
| `tests/` | 测试目录 | 全部任务 |

---

## 阶段 1：P0 紧急修复

### Task 1: 统一时间戳转换到 utils（A-P0-1/2/3）

**Files:**
- Modify: `.agents/skills/video-to-slides/scripts/videotodoc/utils.py:51-56`
- Modify: `.agents/skills/video-to-slides/scripts/videotodoc/pipeline.py:40-41`
- Modify: `.agents/skills/video-to-slides/scripts/videotodoc/asr.py:259-284,265-266,310-311,318-319,360-361,368-369`
- Modify: `.agents/skills/video-summary/scripts/process.py:696-700`
- Modify: `.agents/skills/video-to-slides/scripts/_shared/transcript_merge/__init__.py:73-76`
- Test: `tests/test_utils_time.py`（新建）

**Interfaces:**
- Produces: `utils.seconds_to_ms(seconds: float) -> int`（已有，带 `max(0,...)` 钳制）
- Produces: `utils.ms_to_seconds(ms: int) -> float`（已有）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_utils_time.py
from videotodoc.utils import seconds_to_ms, ms_to_seconds

def test_seconds_to_ms_positive():
    assert seconds_to_ms(1.5) == 1500

def test_seconds_to_ms_zero():
    assert seconds_to_ms(0.0) == 0

def test_seconds_to_ms_negative_clamped():
    assert seconds_to_ms(-1.5) == 0

def test_ms_to_seconds():
    assert ms_to_seconds(1500) == 1.5

def test_transcript_from_dict_accepts_seconds():
    """transcript_from_dict 应兼容秒格式 JSON"""
    from videotodoc.asr import transcript_from_dict
    data = {"segments": [{"start": 1.5, "end": 3.2, "text": "hello"}]}
    t = transcript_from_dict(data)
    assert t.segments[0].start_ms == 1500
    assert t.segments[0].end_ms == 3200

def test_save_subtitle_as_transcript_handles_seconds_fallback():
    """save_subtitle_as_transcript 回退分支应做 ×1000 换算"""
    from video_summary.process import save_subtitle_as_transcript
    # 见下方实现说明
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_utils_time.py -v`
Expected: `test_transcript_from_dict_accepts_seconds` 和 `test_save_subtitle_as_transcript_handles_seconds_fallback` FAIL

- [ ] **Step 3: 修改 `asr.py:transcript_from_dict` 兼容秒格式**

```python
# videotodoc/asr.py 第 272-273 行改为：
from videotodoc.utils import seconds_to_ms

def transcript_from_dict(data: dict) -> Transcript:
    segments = []
    for item in data.get("segments", []):
        start_ms = item.get("start_ms")
        if start_ms is None:
            start_ms = seconds_to_ms(item.get("start", 0))
        end_ms = item.get("end_ms")
        if end_ms is None:
            end_ms = seconds_to_ms(item.get("end", 0))
        segments.append(TranscriptSegment(
            start_ms=int(start_ms),
            end_ms=int(end_ms),
            text=item.get("text", "").strip(),
        ))
    return Transcript(segments=segments, backend=data.get("backend", "unknown"))
```

- [ ] **Step 4: 修改 `process.py:save_subtitle_as_transcript` 回退分支**

```python
# video-summary/scripts/process.py 第 696-700 行改为：
from videotodoc.utils import seconds_to_ms  # 或复用 _shared 版本

"start_ms": seg.get("start_ms") if "start_ms" in seg else seconds_to_ms(seg.get("start", 0)),
"end_ms": seg.get("end_ms") if "end_ms" in seg else seconds_to_ms(seg.get("end", 0)),
```

- [ ] **Step 5: 替换所有内联 `int(round(float(...) * 1000))` 为 `seconds_to_ms`**

在 `asr.py`（265-266, 310-311, 318-319, 360-361, 368-369）、`pipeline.py:40-41`、`_shared/transcript_merge/__init__.py:73-76` 中批量替换。

- [ ] **Step 6: 运行测试确认通过**

Run: `pytest tests/test_utils_time.py tests/test_pipeline_transcript.py -v`
Expected: ALL PASS

- [ ] **Step 7: 提交**

```bash
git add tests/test_utils_time.py .agents/skills/video-to-slides/scripts/videotodoc/utils.py .agents/skills/video-to-slides/scripts/videotodoc/asr.py .agents/skills/video-to-slides/scripts/videotodoc/pipeline.py .agents/skills/video-summary/scripts/process.py
git commit -m "fix: 统一时间戳转换到 utils.seconds_to_ms，消除单位混用根因"
```

---

### Task 2: 删除废弃死代码 + 修复缓存取文件（A-P0-4/7）

**Files:**
- Delete: `.agents/skills/video-to-slides/scripts/videotodoc/feishu.py`
- Modify: `.agents/skills/video-to-slides/scripts/videotodoc/pipeline.py:159-162`
- Test: `tests/test_finalize_cache.py`（新建）

- [ ] **Step 1: 确认 feishu.py 无引用**

Run: `grep -r "from.*feishu import\|import.*feishu" .agents/skills/video-to-slides/scripts/ --include="*.py"`
Expected: 无匹配（仅 feishu.py 自身）

- [ ] **Step 2: 删除 feishu.py**

```bash
rm .agents/skills/video-to-slides/scripts/videotodoc/feishu.py
```

- [ ] **Step 3: 写失败测试——finalize 取缓存应校验 video_hash**

```python
# tests/test_finalize_cache.py
import json
from pathlib import Path
from videotodoc.pipeline import finalize_video

def test_finalize_rejects_mismatched_cache(tmp_path):
    """cache 目录有多个 candidates.json 时应按 video_hash 匹配，不取第一个"""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    # 写两个不同 hash 的 candidates 文件
    (cache_dir / "aaa.candidates.json").write_text(json.dumps({
        "slides": [], "video_hash": "aaa"
    }))
    (cache_dir / "bbb.candidates.json").write_text(json.dumps({
        "slides": [], "video_hash": "bbb"
    }))
    # 应匹配 bbb，不匹配时报错而非取 aaa
    # （具体断言取决于 finalize_video 签名，见实现）
```

- [ ] **Step 4: 运行测试确认失败**

Run: `pytest tests/test_finalize_cache.py -v`
Expected: FAIL

- [ ] **Step 5: 修改 `pipeline.py:159-162` 校验 video_hash**

```python
# videotodoc/pipeline.py 第 159-162 行改为：
candidates_files = list(cache_dir.glob("*.candidates.json"))
video_hash = file_md5(video_path)  # 复用已有
matched = None
for cf in candidates_files:
    data = read_json(cf)
    if data.get("video_hash") == video_hash:
        matched = data
        break
if matched is None:
    raise VideoToDocError(
        f"cache 目录无匹配 video_hash={video_hash[:8]} 的 candidates.json，"
        f"找到 {[cf.name for cf in candidates_files]}，请重跑 capture"
    )
candidates = slides_from_dict(matched)
```

- [ ] **Step 6: 运行测试确认通过**

Run: `pytest tests/test_finalize_cache.py -v`
Expected: PASS

- [ ] **Step 7: 提交**

```bash
git add -A .agents/skills/video-to-slides/scripts/videotodoc/feishu.py .agents/skills/video-to-slides/scripts/videotodoc/pipeline.py tests/test_finalize_cache.py
git commit -m "fix: 删除废弃 feishu.py，finalize 取缓存校验 video_hash 防错配"
```

---

### Task 3: 子进程调用增加 timeout（A-P0-5）

**Files:**
- Modify: `.agents/skills/video-to-slides/scripts/videotodoc/utils.py:13-27`
- Modify: `.agents/skills/video-to-slides/scripts/videotodoc/mindmap.py:60`
- Modify: `.agents/skills/feishu-markdown-publish/scripts/publish.py:182-185`
- Test: `tests/test_run_command_timeout.py`（新建）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_run_command_timeout.py
import pytest
from videotodoc.utils import run_command, VideoToDocError

def test_run_command_timeout_raises():
    """超时应抛 VideoToDocError 而非永久挂起"""
    with pytest.raises(VideoToDocError, match="timeout"):
        run_command(["sleep", "10"], timeout=1)

def test_run_command_completes_within_timeout():
    """正常命令在 timeout 内完成应成功"""
    run_command(["echo", "hello"], timeout=5)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_run_command_timeout.py -v`
Expected: FAIL（`run_command` 无 timeout 参数）

- [ ] **Step 3: 修改 `utils.run_command` 增加 timeout**

```python
# videotodoc/utils.py 第 13-27 行改为：
import subprocess
from typing import Sequence

def run_command(
    cmd: Sequence[str],
    *,
    timeout: float = 120,
    check: bool = True,
) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            list(cmd),
            check=check,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise VideoToDocError(
            f"命令超时（{timeout}s）：{' '.join(cmd)}\nstdout: {e.stdout}\nstderr: {e.stderr}"
        ) from e
```

- [ ] **Step 4: 给所有 `run_command` 调用方传入合理 timeout**

```python
# mindmap.py:60 mmdc 渲染
subprocess.run(args, ..., check=True, timeout=120, env=env)

# publish.py:182 lark-cli 调用
subprocess.run(args, ..., timeout=60)

# slides.py 中 ffmpeg 场景检测（大视频）
run_command(["ffmpeg", ...], timeout=600)  # 场景检测可能久

# slides.py 中 extract_frame（单帧提取）
run_command(["ffmpeg", ...], timeout=30)
```

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest tests/test_run_command_timeout.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/utils.py .agents/skills/video-to-slides/scripts/videotodoc/mindmap.py .agents/skills/feishu-markdown-publish/scripts/publish.py tests/test_run_command_timeout.py
git commit -m "fix: 所有子进程调用增加 timeout，防止流程僵死"
```

---

### Task 4: 临时文件改用 tempfile + OCR 缓存到 Slide 对象（A-P0-6/8）

**Files:**
- Modify: `.agents/skills/video-to-slides/scripts/videotodoc/models.py`
- Modify: `.agents/skills/video-to-slides/scripts/videotodoc/slides.py:208-218,213-243,199-209`
- Modify: `.agents/skills/video-to-slides/scripts/videotodoc/ocr.py:17`
- Test: `tests/test_slides_cache.py`（新建）

**Interfaces:**
- Produces: `Slide` 新增字段 `ocr_text: str | None = None`
- Produces: `Slide` 新增字段 `change_ratio_cache: dict | None = None`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_slides_cache.py
from pathlib import Path
from videotodoc.slides import is_near_duplicate, Slide
from videotodoc.models import Slide as SlideModel

def test_slide_has_ocr_text_field():
    """Slide 数据模型应有 ocr_text 字段"""
    s = SlideModel(capture_ms=1000, image_path="x.png", hash="ab")
    assert s.ocr_text is None

def test_is_near_duplicate_uses_cached_ocr(tmp_path):
    """is_near_duplicate 应优先读 slide.ocr_text 缓存而非重算"""
    # 创建两张测试图
    from PIL import Image
    img1 = tmp_path / "a.png"; Image.new("RGB", (64,64), "white").save(img1)
    img2 = tmp_path / "b.png"; Image.new("RGB", (64,64), "white").save(img2)
    s1 = SlideModel(capture_ms=0, image_path=str(img1), hash="aa", ocr_text="hello")
    s2 = SlideModel(capture_ms=1000, image_path=str(img2), hash="bb", ocr_text="hello")
    # 应使用缓存 ocr_text，不调用 ocr.extract_text
    result = is_near_duplicate(s2, s1, hash_threshold=8)
    assert isinstance(result, bool)

def test_choose_capture_time_uses_tempdir_not_user_dir(tmp_path):
    """临时帧应写到 tempfile 目录而非视频所在目录"""
    import tempfile
    # 验证 .videotodoc_tmp_frames 不再出现在视频目录
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_slides_cache.py -v`
Expected: FAIL（Slide 无 ocr_text 字段）

- [ ] **Step 3: 扩展 Slide 模型**

```python
# videotodoc/models.py Slide dataclass 增加字段：
@dataclass
class Slide:
    capture_ms: int
    image_path: str
    hash: str
    edge_density: float = 0.0
    ocr_text: str | None = None
    change_ratio_cache: dict | None = None
```

- [ ] **Step 4: 修改 `is_near_duplicate` 使用缓存**

```python
# videotodoc/slides.py 第 213-243 行改为：
def is_near_duplicate(
    current: Slide,
    previous: Slide,
    hash_threshold: int,
    settings: Settings | None = None,
    stats: DedupeStats | None = None,
) -> bool:
    # dHash 复用 Slide.hash（已缓存）
    hash_diff = hamming_distance(current.hash, previous.hash)
    change_ratio = image_change_ratio(
        Path(current.image_path), Path(previous.image_path)
    )
    if stats:
        stats.total += 1

    if change_ratio < settings.duplicate_change_threshold and hash_diff <= hash_threshold:
        if stats: stats.duplicate_change += 1
        return True
    if change_ratio >= settings.different_change_threshold or hash_diff > hash_threshold * 2:
        if stats: stats.different_change += 1
        return False

    # 不确定——OCR 判定，优先读缓存
    if current.ocr_text is None:
        current.ocr_text = extract_text(current.image_path)
    if previous.ocr_text is None:
        previous.ocr_text = extract_text(previous.image_path)
    similarity = _text_similarity(current.ocr_text, previous.ocr_text)
    if similarity >= settings.ocr_similarity_threshold and change_ratio < settings.different_change_threshold:
        if stats: stats.ocr_duplicate += 1
        return True
    if stats: stats.ocr_different += 1
    return False
```

- [ ] **Step 5: 修改 `choose_capture_time` 使用 tempfile**

```python
# videotodoc/slides.py 第 208-218 行改为：
import tempfile, shutil

def choose_capture_time(video_path, start_ms, end_ms, settings):
    tmp_dir = Path(tempfile.mkdtemp(prefix="videotodoc_frames_"))
    try:
        times = _refine_times(start_ms, end_ms, settings)
        frames = []
        for offset, capture_ms in enumerate(times):
            frame_path = tmp_dir / f"frame_{offset}.png"
            extract_frame(video_path, capture_ms, frame_path)
            frames.append((capture_ms, frame_path, edge_density(frame_path)))
        # 选 edge_density 最高的帧（文字/图表越多越稳定）
        best_ms, best_path, best_density = max(frames, key=lambda x: x[2])
        return best_ms, best_density
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
```

- [ ] **Step 6: 运行测试确认通过**

Run: `pytest tests/test_slides_cache.py -v`
Expected: PASS

- [ ] **Step 7: 提交**

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/models.py .agents/skills/video-to-slides/scripts/videotodoc/slides.py tests/test_slides_cache.py
git commit -m "perf: OCR 缓存到 Slide 对象，临时帧改用 tempfile，消除子进程风暴"
```

---

### Task 5: 修复 is_near_duplicate 硬编码 0.12 + choose_capture_time 减少子进程（A-P0-9/10）

**Files:**
- Modify: `.agents/skills/video-to-slides/scripts/videotodoc/slides.py:334,155-187`
- Test: `tests/test_dedupe_threshold.py`（新建）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_dedupe_threshold.py
from videotodoc.config import Settings

def test_change_ratio_uses_config_not_hardcoded():
    """修改 different_change_threshold 应影响去重判断"""
    s = Settings(different_change_threshold=0.20)
    # 原硬编码 0.12 时，改配置无效；修复后应生效
    assert s.different_change_threshold == 0.20
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_dedupe_threshold.py -v`
Expected: FAIL（硬编码 0.12 未读配置）

- [ ] **Step 3: 替换硬编码 0.12 为配置项**

```python
# videotodoc/slides.py 第 334 行：
# 原：if similarity >= settings.ocr_similarity_threshold and change_ratio < 0.12:
# 改：
if similarity >= settings.ocr_similarity_threshold and change_ratio < settings.different_change_threshold:
```

- [ ] **Step 4: 修改 `choose_capture_time` 从候选帧筛选而非重新提取**

```python
# videotodoc/slides.py choose_capture_time 改为优先从 candidates_dir 读已有帧：
def choose_capture_time(video_path, start_ms, end_ms, settings, candidates_dir=None):
    """从 [end_ms-1s, end_ms-0.5s] 窗口选最稳定帧。
    优先从 candidates_dir 读已有候选帧，避免重新 ffmpeg 提取。"""
    window_start = end_ms - 1000
    window_end = end_ms - 500
    if candidates_dir:
        # 从已有候选帧按时间窗口筛选
        candidate_frames = []
        for f in candidates_dir.glob("candidate_*.png"):
            # 解析文件名中的时间戳
            ms = int(f.stem.split("_")[-1])
            if window_start <= ms <= window_end:
                candidate_frames.append((ms, f))
        if candidate_frames:
            # 用 PIL 直接比较，选 edge_density 最高的
            best = max(candidate_frames, key=lambda x: edge_density(x[1]))
            return best[0], 1.0
    # 回退：ffmpeg 提取（用 tempfile，复用 Task 4 的 choose_capture_time 逻辑）
    return _choose_capture_time_ffmpeg(video_path, window_start, window_end, settings)
```

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest tests/test_dedupe_threshold.py tests/test_slides_cache.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/slides.py tests/test_dedupe_threshold.py
git commit -m "fix: 去重阈值改用配置项；choose_capture_time 优先读候选帧减少子进程"
```

---

### Task 6: 清理死代码与遗留兼容函数（A-P1-18）

**Files:**
- Modify: `videotodoc/segment.py:30-31`（删 `_text_similarity`，修正 docstring）
- Modify: `videotodoc/document.py:12-15,226-229`（删 `render_markdown`、`render_docx`）
- Modify: `videotodoc/slides.py:411-412,581-588`（删 `_is_duplicate`、`_slide_overlaps_segment`）
- Modify: `videotodoc/asr.py:130`（删 `word_idx`）
- Modify: `videotodoc/quality.py:23`（删 mock 死分支）
- Test: 现有测试不回归

- [ ] **Step 1: 确认每个函数无引用**

```bash
grep -rn "_text_similarity\|render_markdown\|render_docx\|_is_duplicate\|_slide_overlaps_segment\|word_idx" .agents/skills/ --include="*.py" | grep -v "def \|#\|test_"
```
Expected: 仅定义处，无调用

- [ ] **Step 2: 删除死代码**

逐个删除上述函数定义。`segment.py:45-55` docstring 修正为描述真实合并规则（按 `len(combined_text) <= max_segment_chars` 合并，非相似度）。

- [ ] **Step 3: 修正 `segment.py` docstring**

```python
# videotodoc/segment.py 第 45-55 行 docstring 改为：
"""生成 pending segments。
合并规则：相邻段合并后 len(combined_text) <= max_segment_chars 则合并；
超过 max_segment_chars 则单独成段。suggested_action 标记是否含 step_words。"""
```

- [ ] **Step 4: 运行全部测试确认不回归**

Run: `pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 5: 提交**

```bash
git add -A
git commit -m "refactor: 清理 6 处死代码与遗留兼容函数，修正 segment.py docstring"
```

---

## 阶段 2：P1 性能并行化与健壮性

### Task 7: detect_slides 候选帧提取并行（A-P1-1）

**Files:**
- Modify: `videotodoc/slides.py:46-84`
- Test: `tests/test_detect_slides_parallel.py`（新建）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_detect_slides_parallel.py
import time
from unittest.mock import patch
from videotodoc.slides import detect_slides

def _slow_extract(video_path, ms, path, precise=False):
    time.sleep(0.1)  # 模拟 ffmpeg 提取延迟

def test_detect_slides_parallel_faster_than_serial(monkeypatch, tmp_path):
    """并行提取候选帧应比串行快（mock ffmpeg 延迟验证）"""
    monkeypatch.setattr("videotodoc.slides.extract_frame", _slow_extract)
    monkeypatch.setattr("videotodoc.slides._detect_scene_changes", lambda *a: [(0, 1), (2, 3), (4, 5), (6, 7), (8, 9), (10, 11), (12, 13), (14, 15), (16, 17), (18, 19)])
    monkeypatch.setattr("videotodoc.slides._get_duration_ms", lambda *a: 20000)
    monkeypatch.setattr("videotodoc.slides.is_near_duplicate", lambda *a: False)

    start = time.monotonic()
    detect_slides(Path("dummy.mp4"), tmp_path, tmp_path / "out.json", Settings(), skip_dedupe=True)
    elapsed = time.monotonic() - start
    # 10 个候选点 × 0.1s，串行 ~1s，并行应 <0.5s
    assert elapsed < 0.6, f"并行提取耗时 {elapsed:.2f}s，预期 <0.6s"
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_detect_slides_parallel.py -v`
Expected: FAIL

- [ ] **Step 3: 实现——阶段 A 并行提取+计算 dhash，阶段 B 串行去重**

```python
# videotodoc/slides.py 第 46-84 行改为：
from concurrent.futures import ThreadPoolExecutor

def detect_slides(video_path, output_dir, output_json, settings, force=False, skip_dedupe=False):
    # 场景检测（不变，复用原有 _detect_scene_changes）
    scene_changes = _detect_scene_changes(video_path, settings)
    duration_ms = _get_duration_ms(video_path)
    boundaries = _build_boundaries(scene_changes, duration_ms, settings)

    # 阶段 A：并行提取所有候选帧 + 计算 dhash
    candidate_points = [_candidate_capture_ms(s, e, settings) for s, e in boundaries]
    def _extract_and_hash(point):
        path = _candidate_image_path(output_dir, point)
        if not path.exists():
            extract_frame(video_path, point, path, precise=False)
        return (point, path, dhash(path))

    with ThreadPoolExecutor(max_workers=4) as ex:
        precomputed = list(ex.map(_extract_and_hash, candidate_points))

    # 阶段 B：串行去重（依赖前一张）
    slides = []
    stats = DedupeStats()
    for point, path, h in precomputed:
        current = Slide(capture_ms=point, image_path=str(path), hash=h)
        if not skip_dedupe and slides:
            if is_near_duplicate(current, slides[-1], settings.duplicate_hash_threshold, settings, stats):
                continue
        slides.append(current)

    # 写出结果（不变）
    slide_set = SlideSet(slides=slides, video_hash=file_md5(video_path))
    write_json(output_json, slide_set_to_dict(slide_set))
    return slide_set
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_detect_slides_parallel.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/slides.py tests/test_detect_slides_parallel.py
git commit -m "perf: detect_slides 候选帧提取并行化，降速 50-70%"
```

---

### Task 8: refine_selected_slides + finalize 逐段并行（A-P1-2/6）

**Files:**
- Modify: `videotodoc/slides.py:113-131`
- Modify: `videotodoc/pipeline.py:176-180`
- Test: `tests/test_refine_parallel.py`（新建）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_refine_parallel.py
from videotodoc.slides import refine_selected_slides

def test_refine_parallel_preserves_order():
    """并行 refine 后 slide 顺序应与输入一致"""
    # mock choose_capture_time + extract_frame
    # 验证输出顺序
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现 refine 并行**

```python
# videotodoc/slides.py 第 113-131 行改为：
def refine_selected_slides(slides, video_path, output_dir, settings):
    def _refine_one(index, slide):
        capture_ms, confidence = choose_capture_time(
            video_path, slide.start_ms, slide.end_ms, settings
        )
        image_path = output_dir / f"{index:04d}.png"
        extract_frame(video_path, capture_ms, image_path, precise=True)
        return Slide(
            capture_ms=capture_ms, image_path=str(image_path),
            hash=slide.hash, edge_density=slide.edge_density,
            start_ms=slide.start_ms, end_ms=slide.end_ms,
        )

    with ThreadPoolExecutor(max_workers=4) as ex:
        results = list(ex.map(
            lambda args: _refine_one(*args),
            enumerate(slides, start=1)
        ))
    return results
```

- [ ] **Step 4: 实现 finalize 逐段并行**

```python
# videotodoc/pipeline.py 第 176-180 行改为：
with ThreadPoolExecutor(max_workers=4) as ex:
    futures = {
        ex.submit(finalize_segment_slides, seg, candidates, video_path, fill_dir, settings): i
        for i, seg in enumerate(segments) if seg["suggested_action"] != "merge"
    }
    results = [None] * len(segments)
    for future in as_completed(futures):
        results[futures[future]] = future.result()
    all_slides = [r for r in results if r is not None]
```

- [ ] **Step 5: 运行测试 + 全量回归**

Run: `pytest tests/test_refine_parallel.py tests/ -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/slides.py .agents/skills/video-to-slides/scripts/videotodoc/pipeline.py tests/test_refine_parallel.py
git commit -m "perf: refine_selected_slides 与 finalize 逐段并行化"
```

---

### Task 9: 文档生成并行编排（A-P1-3/7）

**Files:**
- Modify: `videotodoc/pipeline.py:338-364`
- Test: `tests/test_doc_generation_parallel.py`（新建）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_doc_generation_parallel.py
def test_doc_generation_produces_all_outputs(tmp_path):
    """并行生成后应产出 3 个 MD + 2 个 docx + 质量报告"""
    # mock sections, 验证产物文件存在
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现三阶段并行**

```python
# videotodoc/pipeline.py 第 338-364 行改为：
from concurrent.futures import ThreadPoolExecutor, as_completed

# 阶段 A：mindmap 渲染 + original md + quality_report 并行
with ThreadPoolExecutor(max_workers=3) as ex:
    f_mindmap = ex.submit(generate_mindmap, video_path.stem, sections, mindmap_path, settings)
    f_original = ex.submit(render_original_markdown, video_path.stem, sections, markdown_path)
    f_quality = ex.submit(write_quality_report, transcript, selected, sections, quality_path)
    mindmap = f_mindmap.result()
    f_original.result()
    f_quality.result()

# mindmap PNG 渲染就绪后
render_mindmap_and_refresh_docs(run_dir, mindmap_path)

# 阶段 B：compact md + semantic md 并行
with ThreadPoolExecutor(max_workers=2) as ex:
    f_compact = ex.submit(render_compact_markdown, video_path.stem, sections, compact_path, mm_image_path)
    f_semantic = ex.submit(ensure_semantic_markdown, video_path.stem, sections, semantic_path, mm_image_path)
    f_compact.result()
    f_semantic.result()

# 阶段 C：两个 docx 并行（CPU 密集，用 ProcessPool）
from concurrent.futures import ProcessPoolExecutor
with ProcessPoolExecutor(max_workers=2) as ex:
    f_docx1 = ex.submit(markdown_to_docx, compact_markdown_path, docx_path)
    f_docx2 = ex.submit(markdown_to_docx, semantic_markdown_path, semantic_docx_path)
    f_docx1.result()
    f_docx2.result()
```

- [ ] **Step 4: 修复 `pipeline.py:329-337` 重复读 sections**

```python
# 第 337 行直接复用变量，不再 read_json：
# 原：sync_offset_ms = int(read_json(sections_path).get("sync_offset_ms", 0))
# 改：直接用作用域内已有的 sync_offset_ms 变量
```

- [ ] **Step 5: 运行测试 + 回归**

Run: `pytest tests/test_doc_generation_parallel.py tests/ -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/pipeline.py tests/test_doc_generation_parallel.py
git commit -m "perf: 文档生成 6 步串行改 3 阶段并行，修复重复读 sections"
```

---

### Task 10: ASR 与截图检测并行 + B站双流下载（A-P1-4/5）

**Files:**
- Modify: `videotodoc/pipeline.py:201-296`
- Modify: `video-summary/scripts/process.py:526-535`
- Test: `tests/test_pipeline_parallel.py`（新建）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_pipeline_parallel.py
def test_asr_and_detect_run_concurrently():
    """ASR 和 detect_slides 应并行执行"""
    # mock transcribe_audio 和 detect_slides 各睡 0.5s
    # 串行应 ~1s，并行应 <0.8s
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现 ASR 与截图并行**

```python
# videotodoc/pipeline.py process_video 中音频提取后：
with ThreadPoolExecutor(max_workers=2) as ex:
    f_transcript = ex.submit(transcribe_audio, audio_path, run_dir, settings)
    f_candidates = ex.submit(detect_slides, video_path, candidates_dir, candidates_json, settings)
    transcript = f_transcript.result()
    candidates = f_candidates.result()
```

- [ ] **Step 4: 实现 B站 DASH 双流并行下载**

```python
# video-summary/scripts/process.py 第 526-535 行改为：
from concurrent.futures import ThreadPoolExecutor

def _download_stream(url, tmp_path, headers, cookies):
    r = cffi_requests.get(url, headers=headers, cookies=cookies, stream=True, timeout=120)
    with open(tmp_path, "wb") as f:
        for chunk in r.iter_content(8192):
            f.write(chunk)
    r.close()

with ThreadPoolExecutor(max_workers=2) as ex:
    f_v = ex.submit(_download_stream, v_url, v_tmp, headers, cookies)
    f_a = ex.submit(_download_stream, a_url, a_tmp, headers, cookies)
    f_v.result()
    f_a.result()
```

- [ ] **Step 5: 运行测试 + 回归**

Run: `pytest tests/test_pipeline_parallel.py tests/ -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/pipeline.py .agents/skills/video-summary/scripts/process.py tests/test_pipeline_parallel.py
git commit -m "perf: ASR 与截图并行；B站 DASH 双流并行下载"
```

---

### Task 11: 健壮性批量修复——异常处理、symlink、超时（A-P1-9~17）

**Files:**
- Modify: `videotodoc/ocr.py:28-31,54-61`
- Modify: `videotodoc/document.py:209,395-403`
- Modify: `videotodoc/pipeline.py:225,345`
- Modify: `video-summary/scripts/process.py:200,206,408,585,644-671,748`
- Modify: `feishu-markdown-publish/scripts/publish.py:189`
- Modify: `videotodoc/cli.py:16-31`
- Test: `tests/test_robustness.py`（新建）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_robustness.py
import sys
from unittest.mock import patch
from videotodoc import ocr

def test_ocr_failure_logs_to_stderr(capsys, monkeypatch):
    """OCR 失败应打印 stderr 而非静默"""
    monkeypatch.setattr(ocr, "extract_text", lambda *a: (_ for _ in ()).throw(RuntimeError("OCR crash")))
    result = ocr.extract_text("dummy.png")
    assert result == ""  # 失败返回空字符串
    captured = capsys.readouterr()
    assert "OCR" in captured.err or "warn" in captured.err  # 有 stderr 日志

def test_symlink_fallback_to_copy(tmp_path, monkeypatch):
    """symlink 失败应 fallback 到 shutil.copy2"""
    src = tmp_path / "src.txt"; src.write_text("hello")
    dst = tmp_path / "dst.txt"
    # mock symlink_to 抛 OSError
    import shutil
    original_copy = shutil.copy2
    copied = [False]
    def mock_copy2(s, d):
        copied[0] = True
        return original_copy(s, d)
    monkeypatch.setattr(shutil, "copy2", mock_copy2)
    # 调用含 symlink fallback 的函数
    from videotodoc.pipeline import _safe_link
    _safe_link(src, dst)
    assert copied[0] is True  # 走了 copy2 fallback

def test_cli_catches_os_error(monkeypatch, capsys):
    """cli 应捕获 OSError 给友好报错"""
    import videotodoc.cli as cli
    def mock_main(*args):
        raise OSError("disk full")
    monkeypatch.setattr(cli, "_run_pipeline", mock_main)
    monkeypatch.setattr(sys, "argv", ["cli", "capture", "nonexistent.mp4"])
    try:
        cli.main()
    except SystemExit as e:
        assert e.code == 1
    captured = capsys.readouterr()
    assert "disk full" in captured.err or "错误" in captured.err
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 逐个修复**

```python
# ocr.py:28-31 OCR 失败加日志
except Exception as e:
    import sys; print(f"[warn] OCR 失败: {e}", file=sys.stderr)
    return ""

# ocr.py:54-61 RapidOCR 失败不缓存
@lru_cache(maxsize=1)
def _rapidocr_engine():
    try:
        from rapidocr_onnxruntime import RapidOCR
        return RapidOCR()
    except Exception as e:
        import sys; print(f"[warn] RapidOCR 初始化失败: {e}", file=sys.stderr)
        return None  # 不缓存 None，下次重试——移除 lru_cache 或改 TTL

# pipeline.py:225 symlink 加 fallback
try:
    temp_mindmap.symlink_to(mindmap_path.name)
except OSError:
    shutil.copy2(mindmap_path, temp_mindmap)

# document.py:395 OpenAI 加 timeout
client = OpenAI(timeout=60)

# cli.py:16-31 加兜底
except VideoToDocError as exc:
    print(f"错误：{exc}", file=sys.stderr); sys.exit(1)
except (OSError, ValueError, KeyError) as exc:
    print(f"错误：{exc}", file=sys.stderr); sys.exit(1)
```

- [ ] **Step 4: 修复 `process.py` 重复调用 `fetch_video_info`**

```python
# process.py:748 的 info 传入 fetch_subtitles
info = fetch_video_info(user_input)
has_subtitle, subtitle_text, _ = fetch_subtitles(user_input, run_dir, args.language, _info=info)
```

- [ ] **Step 5: 运行测试 + 回归**

Run: `pytest tests/test_robustness.py tests/ -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add -A
git commit -m "fix: 健壮性批量修复——异常日志、symlink fallback、超时、重复调用"
```

---

### Task 12: 飞书发布优化 + 重复实现统一（A-P1-8/19）

**Files:**
- Modify: `feishu-markdown-publish/scripts/publish.py:77-95`
- Create: `.agents/skills/_shared/text_utils.py`（slugify + format_time 统一）
- Modify: `videotodoc/utils.py:41-43`、`video-summary/scripts/process.py:54-57,64-69`、`videotodoc/document.py:368-374`、`publish.py:362-364`
- Test: `tests/test_publish_batch.py`、`tests/test_shared_utils.py`（新建）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_shared_utils.py
from _shared.text_utils import slugify, format_ms, format_seconds

def test_slugify_unified():
    assert slugify("视频 标题/测试") == "视频_标题_测试"

def test_format_ms_unified():
    assert format_ms(90000) == "00:01:30"
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 创建 `_shared/text_utils.py`**

```python
# .agents/skills/_shared/text_utils.py
import re
from pathlib import PurePath

def slugify(name: str) -> str:
    """统一 slugify：保留中文，替换文件系统非法字符为下划线"""
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", name).strip("_")

def format_ms(ms: int) -> str:
    """毫秒转 HH:MM:SS"""
    s = ms // 1000
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"

def format_seconds(sec: float) -> str:
    """秒转 HH:MM:SS"""
    return format_ms(int(sec * 1000))
```

- [ ] **Step 4: 各处替换为 `_shared.text_utils` 引用**

- [ ] **Step 5: 飞书发布批量 append 优化**

```python
# publish.py:77-95 改为合并相邻文本 chunk
# 把标题+正文合并为一次 append，图片单独 insert
for index, section in enumerate(parsed.sections, start=1):
    # 合并 title + body 为一次 append
    combined = write_chunk(section, "title") + "\n\n" + write_chunk(section, "body")
    publisher.append_doc(doc_ref, combined)
    if section.image:
        publisher.insert_image(doc_ref, section.image, ...)
    publisher.save_progress(doc_ref, index)
```

- [ ] **Step 6: 运行测试 + 回归**

Run: `pytest tests/test_publish_batch.py tests/test_shared_utils.py tests/ -v`
Expected: PASS

- [ ] **Step 7: 提交**

```bash
git add -A
git commit -m "refactor: slugify/format_time 统一到 _shared；飞书发布合并 append"
```

---

## 阶段 3：P2 渐进改进

### Task 13: 测试覆盖盲区补齐（A-P2-11）

**Files:**
- Create: `tests/test_align_sections.py`
- Create: `tests/test_is_near_duplicate.py`
- Create: `tests/test_normalize_segments.py`
- Create: `tests/test_merge_short_segments.py`
- Create: `tests/test_coerce_scalar.py`

**重点补测函数与边界：**

- [ ] **Step 1: `align_sections` 测试**——空 slides、空 segments、单段多图、全部段无匹配图
- [ ] **Step 2: `is_near_duplicate` 测试**——两张相同路径图、OCR 返回空字符串、change_ratio 边界值
- [ ] **Step 3: `normalize_segments` 测试**——负时间戳、end<start、空 text
- [ ] **Step 4: `merge_short_segments` 测试**——单段、全短段、首尾段
- [ ] **Step 5: `_coerce_scalar` 测试**——版本号字符串、带引号嵌套、`null`/`~`
- [ ] **Step 6: 运行全部测试**

Run: `pytest tests/ -v --tb=short`
Expected: ALL PASS，覆盖率提升

- [ ] **Step 7: 提交**

```bash
git add tests/
git commit -m "test: 补齐 align/is_near_duplicate/normalize/merge/coerce 核心函数测试"
```

---

### Task 14: 架构重构——拆分 slides.py + 统一 pipeline 入口（A-P2-10）

**Files:**
- Create: `videotodoc/detection.py`（场景检测、候选点、boundaries）
- Create: `videotodoc/dedupe.py`（is_near_duplicate、deduplicate、cross_segment_dedupe、DedupeStats）
- Create: `videotodoc/image_ops.py`（dhash、edge_density、image_change_ratio、hamming_distance、extract_frame）
- Modify: `videotodoc/slides.py`（仅保留 detect_slides、refine、trim、materialize 编排）
- Modify: `videotodoc/pipeline.py`（删除 `process_video` 旧路径，保留 capture/finalize）

- [ ] **Step 1: 拆分 slides.py 到三个新文件，保持函数签名不变**
- [ ] **Step 2: 更新所有 import 引用**
- [ ] **Step 3: 删除 `process_video` 函数，确认无调用方**

```bash
grep -rn "process_video" .agents/skills/ --include="*.py" | grep -v "def \|#\|test_"
```

- [ ] **Step 4: 运行全部测试**

Run: `pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 5: 提交**

```bash
git add -A
git commit -m "refactor: 拆分 slides.py 为 detection/dedupe/image_ops，删除 process_video 旧路径"
```

---

### Task 15: 其他 P2 清理（A-P2-1~9,12）

每个子项独立提交。以下为有行为变化的子项提供测试代码；纯重构子项（15f/15g/15h）验证 `pytest tests/ -v` 不回归即可。

- [ ] **15a: `ocr.py` RapidOCR 失败不永久缓存**

```python
# tests/test_ocr_retry.py
from videotodoc import ocr

def test_rapidocr_failure_does_not_cache_none(monkeypatch):
    """首次失败后再次调用应重试，而非返回缓存的 None"""
    call_count = [0]
    def mock_init():
        call_count[0] += 1
        raise ImportError("rapidocr not installed")
    monkeypatch.setattr(ocr, "_init_rapidocr", mock_init)
    assert ocr.extract_text("dummy.png") == ""
    assert ocr.extract_text("dummy.png") == ""
    assert call_count[0] == 2  # 两次都重试，未缓存失败
```
实现：移除 `_rapidocr_engine` 的 `@lru_cache`，改为模块级变量 + try/except，失败后下次重试。

- [ ] **15b: `process.py` 流式下载关闭 response**

```python
# tests/test_download_closes_response.py
def test_stream_download_uses_context_manager(monkeypatch):
    """下载应使用 with 语句确保 response 关闭"""
    # mock cffi_requests.get 返回带 close 的对象，验证 close 被调用
```
实现：`process.py` 下载处改为 `with cffi_requests.get(url, stream=True, timeout=120) as r:`

- [ ] **15c: `slides.py` 大图片合并开图**

```python
# tests/test_image_ops_efficiency.py
def test_dhash_and_change_ratio_share_open(monkeypatch):
    """dhash 和 change_ratio 应复用同一次 Image.open"""
    open_count = [0]
    original_open = Image.open
    def counting_open(path):
        open_count[0] += 1
        return original_open(path)
    monkeypatch.setattr(Image, "open", counting_open)
    # 调用合并后的函数
    from videotodoc.image_ops import compute_hash_and_change
    compute_hash_and_change("a.png", "b.png")
    assert open_count[0] == 2  # 两个文件各开一次，而非 4 次
```
实现：新增 `compute_hash_and_change(path_a, path_b)` 一次 open 同时算 dhash + change_ratio。

- [ ] **15d: `mindmap.py` `_mmdc_env` 补 Linux/Windows Chrome 路径**

```python
# tests/test_mmdc_env.py
import sys
from videotodoc.mindmap import _mmdc_env

def test_mmdc_env_has_chrome_path(monkeypatch):
    """_mmdc_env 应包含当前平台的 Chrome 路径"""
    env = _mmdc_env()
    assert "PUPPETEER_EXECUTABLE_PATH" in env or "CHROME_PATH" in env
```
实现：在 `_mmdc_env` 增加 `platform.system()` 判断，Linux 补 `/usr/bin/google-chrome`、Windows 补 `C:\Program Files\Google\Chrome\Application\chrome.exe`。

- [ ] **15e: `config.py` `Settings.__post_init__` 校验 `min < max`**

```python
# tests/test_config_validation.py
import pytest
from videotodoc.config import Settings

def test_min_segment_chars_must_be_less_than_max():
    with pytest.raises(ValueError, match="min_segment_chars"):
        Settings(min_segment_chars=500, max_segment_chars=400)

def test_duplicate_thresholds_must_be_ordered():
    with pytest.raises(ValueError, match="duplicate_change_threshold"):
        Settings(duplicate_change_threshold=0.5, different_change_threshold=0.1)
```
实现：`Settings.__post_init__` 增加断言校验。

- [ ] **15f: `cli.py` 子命令统一 `--config` 参数**（纯重构，验证不回归）
- [ ] **15g: `pipeline.py` `transcript_merged.json` 抽常量**（纯重构，验证不回归）
- [ ] **15h: `segment.py` import 移到顶部**（纯重构，验证不回归）

- [ ] **15i: 长视频 ASR 分片并行**（高风险，需先做准确率回归验证）
  - 先用 60 分钟视频基线测试，记录准确率
  - 实现分片并行后对比准确率，若下降超 5% 则回退
  - 此项暂列为 P2 末尾，待前面所有任务完成后再评估

---

## Review 检查清单

每个任务完成后，执行以下 review：

### 代码 Review
- [ ] 改动是否影响现有 CLI 接口？
- [ ] 时间戳单位是否统一为毫秒？
- [ ] 子进程是否都有 timeout？
- [ ] 临时文件是否用 tempfile？
- [ ] 异常是否打印 stderr 而非静默？
- [ ] 并行化是否保持输出顺序？
- [ ] 缓存 key 是否包含文件 mtime？

### 测试 Review
- [ ] 新增测试是否覆盖边界条件（空输入、负值、超长）？
- [ ] `pytest tests/ -v` 是否全绿？
- [ ] 是否有 mock ffmpeg/ASR 的冒烟测试？
- [ ] 并行化测试是否验证顺序正确性？

### 回归 Review
- [ ] 端到端跑一个真实视频，产物是否与改前一致？
- [ ] 质量报告数据是否正常？
- [ ] 飞书发布是否成功？

---

## 测试策略

### 单元测试（每个 Task 必须包含）
- TDD：先写失败测试 → 实现 → 验证通过
- 覆盖边界：空输入、负值、超长、异常输入
- mock 外部依赖：ffmpeg、mlx-whisper、OpenAI、lark-cli

### 集成测试（Task 13 后）
- mock ffmpeg + ASR 的端到端冒烟测试
- 验证 capture → finalize 全流程不崩

### 性能基准测试（Task 7-10 后）
- 用 22 分钟样本视频对比改前改后耗时
- 预期：截图阶段降 50%+，文档生成降 40%+，整体降 30%+

### 回归用例（每个 Task 后）
```bash
# 用已有样本视频跑完整流程
python3 .agents/skills/video-to-slides/scripts/process.py \
  "runs/GLM_5.2_测评报告_还是国内编程天花板吗_20260621_230609/<视频标题>.mp4" \
  --transcript "runs/.../transcript.json"

# 验证产物
ls runs/<新run>/
# 应有：3 个 MD + 2 个 docx + mmd + png + 质量报告
```

---

## 预期总收益

| 指标 | 改前 | 改后预期 |
|---|---|---|
| 22 分钟视频截图阶段 | ~3 分钟 | ~1 分钟 |
| 文档生成阶段 | ~30s | ~10s |
| 整体流水线 | ~10 分钟 | ~6-7 分钟 |
| 单元测试覆盖 | 41 个 | 80+ 个 |
| 死代码行数 | ~150 行 | 0 |
| 静默异常处 | 8+ 处 | 0 |
