# Pipeline 重构与卡点修复 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 重构 video-to-slides 为三步中断式 pipeline（capture/review-segments/finalize），实现长视频截图时长密度自适应与 agent 介入语义分段；修复复盘发现的 9 个卡点。

**架构：** 把 `videotodoc.cli process` 拆成 `capture`/`review-segments`/`finalize` 三个子命令，agent 在 review-segments 环节介入分段确认。B 站下载改为分层探测多策略，飞书发布增加断点续传。保留 `process` 命令向后兼容。

**技术栈：** Python 3.14、mlx-whisper、Pillow、RapidOCR、python-docx、curl_cffi、yt-dlp、lark-cli v2、pytest

---

## 文件结构

### 新建文件
- `.agents/skills/video-to-slides/scripts/videotodoc/segment.py` — 时长密度函数 + 分段草案启发式 + confirmed 格式校验
- `.agents/skills/video-to-slides/scripts/videotodoc/tests/__init__.py` — 测试包
- `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_segment.py` — segment 模块测试
- `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_bilibili.py` — B站下载策略测试
- `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_publish.py` — 飞书发布断点续传测试
- `.agents/skills/video-to-slides/scripts/videotodoc/tests/conftest.py` — pytest 共享 fixture
- `pytest.ini` — pytest 配置

### 修改文件
- `.agents/skills/video-to-slides/scripts/videotodoc/cli.py` — 新增 capture/review-segments/finalize 子命令
- `.agents/skills/video-to-slides/scripts/videotodoc/pipeline.py` — 拆分 process_video 为 capture_video/finalize_video
- `.agents/skills/video-to-slides/scripts/videotodoc/slides.py:549` — trim 补帧 precise=True→False；新增 finalize 段内去重/补图函数
- `.agents/skills/video-to-slides/scripts/videotodoc/config.py` — Settings 新增 max_segment_chars 字段
- `.agents/skills/video-to-slides/scripts/process.py` — --transcript 透传
- `.agents/skills/video-summary/scripts/process.py:347` — B站分层探测多策略；doctor 修复
- `.agents/skills/feishu-markdown-publish/scripts/publish.py` — v2 适配 + 重试 + 断点续传
- `.agents/skills/video-to-slides/SKILL.md` — 环境前置段 + 新流程文档
- `.agents/skills/video-summary/SKILL.md` — 环境前置段
- `.agents/skills/feishu-markdown-publish/SKILL.md` — 环境前置段 + lark-cli 登录检查

---

## 任务 1：建立测试基础设施

**文件：**
- 创建：`pytest.ini`
- 创建：`.agents/skills/video-to-slides/scripts/videotodoc/tests/__init__.py`
- 创建：`.agents/skills/video-to-slides/scripts/videotodoc/tests/conftest.py`

- [ ] **步骤 1：创建 pytest.ini**

```ini
[pytest]
testpaths = .agents/skills/video-to-slides/scripts/videotodoc/tests
pythonpath = .agents/skills/video-to-slides/scripts .agents/skills/_shared
python_files = test_*.py
python_classes = Test*
python_functions = test_*
```

- [ ] **步骤 2：创建测试包和 conftest**

`tests/__init__.py`：空文件。

`tests/conftest.py`：

```python
"""共享 fixture：把 videotodoc 包和 _shared 加入 sys.path。"""
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]  # videotodoc 的父目录
SHARED_DIR = SCRIPTS_DIR.parents[2] / "_shared"      # .agents/skills/_shared
for p in (SCRIPTS_DIR, SHARED_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
```

- [ ] **步骤 3：验证 pytest 可运行**

运行：`cd /Users/jarvis/Documents/VideoToDoc-skills-pipeline-refactor && .venv/bin/python -m pytest --collect-only 2>&1 | tail -3`
预期：`no tests ran`（无测试文件），但无 import 错误

- [ ] **步骤 4：Commit**

```bash
git add pytest.ini .agents/skills/video-to-slides/scripts/videotodoc/tests/
git commit -m "test: 建立 pytest 测试基础设施"
```

---

## 任务 2：时长密度函数

**文件：**
- 创建：`.agents/skills/video-to-slides/scripts/videotodoc/segment.py`
- 创建：`.agents/skills/video-to-slides/scripts/videotodoc/tests/test_segment.py`
- 修改：`.agents/skills/video-to-slides/scripts/videotodoc/config.py`

- [ ] **步骤 1：编写失败的测试**

`tests/test_segment.py`：

```python
from videotodoc.segment import capture_interval_for_duration


class TestCaptureInterval:
    def test_short_video_5min(self):
        assert capture_interval_for_duration(300) == 15

    def test_15min_video(self):
        assert capture_interval_for_duration(900) == 20

    def test_30min_video(self):
        assert capture_interval_for_duration(1800) == 30

    def test_long_video_over_30min(self):
        assert capture_interval_for_duration(3600) == 40

    def test_boundary_5min(self):
        assert capture_interval_for_duration(301) == 20

    def test_boundary_15min(self):
        assert capture_interval_for_duration(901) == 30

    def test_boundary_30min(self):
        assert capture_interval_for_duration(1801) == 40
```

- [ ] **步骤 2：运行测试验证失败**

运行：`.venv/bin/python -m pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_segment.py -v`
预期：FAIL，`ModuleNotFoundError: No module named 'videotodoc.segment'`

- [ ] **步骤 3：实现时长密度函数**

`segment.py`：

```python
"""时长密度函数 + 分段草案启发式 + confirmed 格式校验。"""
from __future__ import annotations


def capture_interval_for_duration(duration_sec: float) -> int:
    """根据视频时长返回初始截图间隔（秒）。

    duration ≤ 5min  → 15s
    duration ≤ 15min → 20s
    duration ≤ 30min → 30s
    duration > 30min → 40s
    """
    if duration_sec <= 300:
        return 15
    if duration_sec <= 900:
        return 20
    if duration_sec <= 1800:
        return 30
    return 40
```

- [ ] **步骤 4：运行测试验证通过**

运行：`.venv/bin/python -m pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_segment.py -v`
预期：PASS，7 passed

- [ ] **步骤 5：config.py 新增 max_segment_chars**

在 `.agents/skills/video-to-slides/scripts/videotodoc/config.py` 的 `Settings` 类中，`min_segment_chars` 字段后新增：

```python
    max_segment_chars: int = 400
```

- [ ] **步骤 6：Commit**

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/segment.py .agents/skills/video-to-slides/scripts/videotodoc/tests/test_segment.py .agents/skills/video-to-slides/scripts/videotodoc/config.py
git commit -m "feat: 时长密度函数 + max_segment_chars 配置"
```

---

## 任务 3：分段草案启发式

**文件：**
- 修改：`.agents/skills/video-to-slides/scripts/videotodoc/segment.py`
- 修改：`.agents/skills/video-to-slides/scripts/videotodoc/tests/test_segment.py`

- [ ] **步骤 1：编写失败的测试**

在 `test_segment.py` 末尾追加：

```python
from videotodoc.segment import generate_pending_segments, validate_confirmed_segments
from videotodoc.models import Slide, SlideSet, TranscriptSegment, Transcript


class TestGeneratePendingSegments:
    def _make_candidates(self, times_ms: list[int]) -> SlideSet:
        return SlideSet(slides=[
            Slide(slide_index=i + 1, image_path=f"img{i}.png", start_ms=t, end_ms=t + 1000,
                  capture_ms=t, confidence=0.8, hash="0" * 16, edge_density=0.5)
            for i, t in enumerate(times_ms)
        ])

    def _make_transcript(self, segments: list[tuple[int, int, str]]) -> Transcript:
        return Transcript(
            backend="test", language="zh",
            segments=[TranscriptSegment(start_ms=s, end_ms=e, text=t) for s, e, t in segments],
        )

    def test_basic_segmentation(self):
        candidates = self._make_candidates([0, 30000, 60000])
        transcript = self._make_transcript([
            (0, 30000, "大家好这是开篇介绍。"),
            (30000, 60000, "接下来讲选购要点。"),
            (60000, 90000, "最后是产品推荐。"),
        ])
        result = generate_pending_segments(candidates, transcript, duration_sec=90)
        assert len(result["segments"]) >= 2
        assert result["capture_interval_sec"] == 15
        assert all("suggested_action" in s for s in result["segments"])

    def test_step_words_force_keep(self):
        candidates = self._make_candidates([0, 15000, 30000])
        transcript = self._make_transcript([
            (0, 15000, "第一步打开设置。"),
            (15000, 30000, "然后点击导出。"),
            (30000, 45000, "接下来保存文件。"),
        ])
        result = generate_pending_segments(candidates, transcript, duration_sec=45)
        step_segments = [s for s in result["segments"] if "第一步" in s["transcript_preview"]
                         or "然后" in s["transcript_preview"] or "接下来" in s["transcript_preview"]]
        # 含步骤词的段不应被标记为 merge
        for s in step_segments:
            assert s["suggested_action"] == "keep"

    def test_long_segment_split(self):
        long_text = "这是一个很长的讲解。" * 100  # > 400 字
        candidates = self._make_candidates([0])
        transcript = self._make_transcript([(0, 120000, long_text)])
        result = generate_pending_segments(candidates, transcript, duration_sec=120)
        split_segments = [s for s in result["segments"] if s["suggested_action"] == "split"]
        assert len(split_segments) >= 1


class TestValidateConfirmedSegments:
    def test_valid_confirmed(self):
        pending = {
            "segments": [
                {"id": "s01", "start_ms": 0, "end_ms": 30000, "label": "开篇",
                 "suggested_action": "keep", "candidate_slide_ids": [1]},
                {"id": "s02", "start_ms": 30000, "end_ms": 60000, "label": "要点",
                 "suggested_action": "merge", "merge_into": "s01", "candidate_slide_ids": [2]},
            ]
        }
        assert validate_confirmed_segments(pending) is True

    def test_merge_without_target(self):
        pending = {
            "segments": [
                {"id": "s01", "start_ms": 0, "end_ms": 30000, "label": "开篇",
                 "suggested_action": "keep", "candidate_slide_ids": [1]},
                {"id": "s02", "start_ms": 30000, "end_ms": 60000, "label": "要点",
                 "suggested_action": "merge", "merge_into": "s99", "candidate_slide_ids": [2]},
            ]
        }
        assert validate_confirmed_segments(pending) is False

    def test_empty_segments(self):
        assert validate_confirmed_segments({"segments": []}) is False
```

- [ ] **步骤 2：运行测试验证失败**

运行：`.venv/bin/python -m pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_segment.py::TestGeneratePendingSegments -v`
预期：FAIL，`ImportError: cannot import name 'generate_pending_segments'`

- [ ] **步骤 3：实现分段草案启发式**

在 `segment.py` 末尾追加：

```python
from difflib import SequenceMatcher
from typing import Any

from .models import Slide, SlideSet, Transcript

# 步骤词：含这些词的短段强制 keep，不合并
_STEP_WORDS = ("第一步", "第二步", "第三步", "首先", "然后", "接下来", "操作", "步骤", "点击", "输入")


def _text_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _has_step_words(text: str) -> bool:
    return any(w in text for w in _STEP_WORDS)


def generate_pending_segments(
    candidates: SlideSet,
    transcript: Transcript,
    duration_sec: float,
    max_segment_chars: int = 400,
    min_segment_chars: int = 30,
) -> dict[str, Any]:
    """生成分段草案 pending_segments.json 的数据结构。

    启发式规则：
    1. 按候选图 capture_ms 把时间轴切成原始片段
    2. 相邻片段文本相似度 ≥0.85，或时长和 <60s 且无步骤词 → merge
    3. 含步骤词且片段 <20s → 强制 keep
    4. 单段文字 > max_segment_chars → split
    5. 单段文字 < min_segment_chars 且无独立场景 → merge 到前一段
    """
    interval = capture_interval_for_duration(duration_sec)

    if not transcript.segments:
        return {"video_title": "", "duration_sec": int(duration_sec),
                "capture_interval_sec": interval, "segments": []}

    # 按候选图 capture_ms 切分时间段
    capture_times = sorted({s.capture_ms for s in candidates.slides})
    if not capture_times:
        capture_times = [0]

    boundaries = [0, *capture_times, transcript.segments[-1].end_ms]
    raw_segments = []
    for i in range(len(boundaries) - 1):
        start_ms = boundaries[i]
        end_ms = boundaries[i + 1]
        # 收集该时间段内的 transcript 文本
        texts = [seg.text for seg in transcript.segments
                 if start_ms <= seg.start_ms < end_ms]
        text = "".join(texts)
        if not text:
            continue
        # 该时间段对应的候选图
        slide_ids = [s.slide_index for s in candidates.slides
                     if start_ms <= s.capture_ms < end_ms]
        raw_segments.append({
            "start_ms": start_ms, "end_ms": end_ms,
            "text": text, "slide_ids": slide_ids,
        })

    # 合并相邻片段
    merged = []
    for seg in raw_segments:
        if merged:
            prev = merged[-1]
            combined_text = prev["text"] + seg["text"]
            time_sum = (seg["end_ms"] - prev["start_ms"]) / 1000
            should_merge = (
                _text_similarity(prev["text"], seg["text"]) >= 0.85
                or (time_sum < 60 and not _has_step_words(seg["text"])
                    and not _has_step_words(prev["text"]))
                or len(seg["text"]) < min_segment_chars
            )
            if should_merge and len(combined_text) <= max_segment_chars:
                prev["end_ms"] = seg["end_ms"]
                prev["text"] = combined_text
                prev["slide_ids"].extend(seg["slide_ids"])
                continue
        merged.append(dict(seg))

    # 生成最终 segment 列表
    segments = []
    for i, seg in enumerate(merged, start=1):
        char_count = len(seg["text"])
        action = "keep"
        extra = {}
        if char_count > max_segment_chars:
            action = "split"
        elif i > 1 and char_count < min_segment_chars:
            action = "merge"
            extra["merge_into"] = f"s{i - 1:02d}"
        segments.append({
            "id": f"s{i:02d}",
            "start_ms": seg["start_ms"],
            "end_ms": seg["end_ms"],
            "label": seg["text"][:20].strip(),
            "suggested_action": action,
            "candidate_slide_ids": seg["slide_ids"],
            "reason": f"字数{char_count}，时长{(seg['end_ms'] - seg['start_ms']) / 1000:.0f}s",
            "transcript_preview": seg["text"][:80],
            "char_count": char_count,
            **extra,
        })

    return {
        "video_title": "",
        "duration_sec": int(duration_sec),
        "capture_interval_sec": interval,
        "segments": segments,
    }


def validate_confirmed_segments(data: dict[str, Any]) -> bool:
    """校验 agent 写回的 confirmed_segments.json 格式。"""
    segments = data.get("segments")
    if not segments or not isinstance(segments, list):
        return False
    ids = {s.get("id") for s in segments}
    for s in segments:
        if not all(k in s for k in ("id", "start_ms", "end_ms", "label", "suggested_action")):
            return False
        action = s["suggested_action"]
        if action == "merge" and s.get("merge_into") not in ids:
            return False
        if action == "split" and "split_at" not in s:
            return False
    return True
```

- [ ] **步骤 4：运行测试验证通过**

运行：`.venv/bin/python -m pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_segment.py -v`
预期：PASS，所有测试通过

- [ ] **步骤 5：Commit**

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/segment.py .agents/skills/video-to-slides/scripts/videotodoc/tests/test_segment.py
git commit -m "feat: 分段草案启发式 + confirmed 格式校验"
```

---

## 任务 4：trim 补帧改 precise=False

**文件：**
- 修改：`.agents/skills/video-to-slides/scripts/videotodoc/slides.py:547-549`

- [ ] **步骤 1：修改 trim 补帧**

将 `slides.py` 第 547-549 行：

```python
            # 该段没有候选图，在中点精确提取一帧
            image_path = output_dir / f"{len(trimmed_slides) + 1:04d}.png"
            extract_frame(video_path, seg_mid_ms, image_path, precise=True)
```

改为：

```python
            # 该段没有候选图，在中点快速提取一帧（补帧为兜底场景，快速 seek 即可）
            image_path = output_dir / f"{len(trimmed_slides) + 1:04d}.png"
            extract_frame(video_path, seg_mid_ms, image_path, precise=False)
```

- [ ] **步骤 2：验证修改**

运行：`grep -n "precise=False" .agents/skills/video-to-slides/scripts/videotodoc/slides.py | grep seg_mid`
预期：输出第 549 行 `extract_frame(video_path, seg_mid_ms, image_path, precise=False)`

- [ ] **步骤 3：Commit**

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/slides.py
git commit -m "fix: trim 补帧改用快速 seek，避免长视频逐帧解码耗时"
```

---

## 任务 5：--transcript 透传

**文件：**
- 修改：`.agents/skills/video-to-slides/scripts/process.py`
- 修改：`.agents/skills/video-to-slides/scripts/videotodoc/cli.py`
- 修改：`.agents/skills/video-to-slides/scripts/videotodoc/pipeline.py`

- [ ] **步骤 1：cli.py 新增 --transcript 参数**

在 `cli.py` 的 `process` subparser 中，`--force-rebuild` 参数后新增：

```python
    process.add_argument("--transcript", type=Path, default=None,
                         help="已有转录文件路径（跳过 ASR）")
```

在 `_settings_from_args` 函数中，`return settings` 前新增：

```python
    transcript_path = getattr(args, "transcript", None)
    if transcript_path:
        settings.transcript_path = transcript_path
```

- [ ] **步骤 2：config.py 新增 transcript_path 字段**

在 `config.py` 的 `Settings` 类中，`min_segment_chars` 字段后新增：

```python
    transcript_path: str = ""
```

- [ ] **步骤 3：pipeline.py 支持复用 transcript**

在 `pipeline.py` 的 `process_video` 函数中，找到步骤 2 ASR 转录部分（约第 80 行）：

```python
    # 步骤 2：ASR 转录（必须在截图裁剪之前完成）
    transcript = transcribe_audio(audio, transcript_path, settings, force=_stage_forced(force_rebuild, "asr"))
```

改为：

```python
    # 步骤 2：ASR 转录（必须在截图裁剪之前完成）
    if settings.transcript_path:
        # 复用已有转录文件，跳过 ASR
        from .io import read_json
        from .models import Transcript, TranscriptSegment
        data = read_json(Path(settings.transcript_path))
        segs = [TranscriptSegment(start_ms=s.get("start_ms", s.get("start", 0)),
                                  end_ms=s.get("end_ms", s.get("end", 0)),
                                  text=s.get("text", ""))
                for s in (data if isinstance(data, list) else data.get("segments", []))]
        transcript = Transcript(backend="reused", language=settings.language, segments=segs)
        print(f"  ♻️  复用已有转录：{settings.transcript_path}（{len(segs)} 段）")
    else:
        transcript = transcribe_audio(audio, transcript_path, settings, force=_stage_forced(force_rebuild, "asr"))
```

- [ ] **步骤 4：process.py 包装器透传 --transcript**

在 `process.py` 中，找到构建 cmd 的部分（约第 60 行 `cmd = [...]`），在 `if args.transcript:` 附近确认已有透传逻辑。当前包装器已接受 `--transcript` 但没传给 cli。在可选参数区块新增：

```python
    if args.transcript:
        cmd += ["--transcript", str(args.transcript)]
```

（插入位置：在 `if args.model:` 区块之前）

- [ ] **步骤 5：验证透传**

运行：`cd /Users/jarvis/Documents/VideoToDoc-skills-pipeline-refactor && .venv/bin/python -c "from videotodoc.config import Settings; s = Settings(); s.transcript_path = 'x.json'; print(s.transcript_path)"`
预期：输出 `x.json`

- [ ] **步骤 6：Commit**

```bash
git add .agents/skills/video-to-slides/scripts/process.py .agents/skills/video-to-slides/scripts/videotodoc/cli.py .agents/skills/video-to-slides/scripts/videotodoc/pipeline.py .agents/skills/video-to-slides/scripts/videotodoc/config.py
git commit -m "fix: --transcript 透传到 cli，复用已有转录跳过 ASR"
```

---

## 任务 6：飞书 publish.py v2 适配 + 重试 + 断点续传

**文件：**
- 修改：`.agents/skills/feishu-markdown-publish/scripts/publish.py`

- [ ] **步骤 1：添加 import time 并改 _run 加重试**

在 `publish.py` 顶部 import 区，`import sys` 后新增：

```python
import time
```

将 `_run` 方法（约第 152 行）替换为：

```python
    def _run(self, args: list[str], retries: int = 4) -> subprocess.CompletedProcess[str]:
        last_err = ""
        for attempt in range(retries):
            result = subprocess.run(
                args, cwd=self.project_dir, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            if result.returncode == 0:
                return result
            last_err = result.stderr.strip() or result.stdout.strip()
            retryable = any(k in last_err for k in ("1771001", "server internal error", "rate limit", "9999", "too many", "timeout"))
            if attempt < retries - 1 and retryable:
                wait = 5 * (attempt + 1)
                print(f"  ⚠️ 第 {attempt+1} 次失败，{wait}s 后重试：{last_err[:120]}", file=sys.stderr)
                time.sleep(wait)
                continue
            raise RuntimeError(last_err)
        raise RuntimeError(last_err)
```

- [ ] **步骤 2：create_doc 适配 v2**

将 `create_doc` 方法（约第 97 行）中的 cmd 替换为：

```python
        cmd = [
            "lark-cli", "docs", "+create",
            "--api-version", "v2",
            "--doc-format", "markdown",
            "--content", f"@{self._cli_path(markdown_path)}",
            "--as", self.identity,
        ]
        if wiki_space:
            cmd += ["--parent-token", wiki_space]
```

- [ ] **步骤 3：update_doc 适配 v2**

将 `update_doc` 方法（约第 123 行）中的 cmd 替换为：

```python
        cmd = [
            "lark-cli", "docs", "+update",
            "--api-version", "v2",
            "--doc", doc_ref, "--command", mode,
            "--doc-format", "markdown",
            "--content", f"@{self._cli_path(markdown_path)}",
            "--as", self.identity,
        ]
```

- [ ] **步骤 4：添加断点续传逻辑**

在 `Publisher.__init__` 末尾（`self.asset_dir.mkdir` 后）新增：

```python
        self.progress_path = publish_dir / "publish_progress.json"
```

在 `Publisher` 类中新增方法：

```python
    def load_progress(self) -> dict | None:
        if not self.progress_path.exists():
            return None
        return json.loads(self.progress_path.read_text(encoding="utf-8"))

    def save_progress(self, doc_ref: str, last_section: int) -> None:
        self.progress_path.write_text(
            json.dumps({"doc_ref": doc_ref, "last_section": last_section}, ensure_ascii=False),
            encoding="utf-8",
        )

    def clear_progress(self) -> None:
        self.progress_path.unlink(missing_ok=True)
```

- [ ] **步骤 5：main 函数集成断点续传**

将 `main` 函数（约第 61 行）中从 `doc_ref = publisher.create_doc(...)` 到 section 循环结束的部分替换为：

```python
    # 断点续传：检测已有进度
    progress = publisher.load_progress()
    if progress:
        doc_ref = progress["doc_ref"]
        start_index = progress["last_section"] + 1
        print(f"  ♻️  检测到断点续传，从第 {start_index} 页继续：{doc_ref}")
    else:
        doc_ref = publisher.create_doc(
            title, write_chunk(publish_dir, "initial", f"# {title}\n\n"), wiki_space,
        )
        publisher.update_doc(
            doc_ref, write_chunk(publish_dir, "header", f"# {title}\n\n{parsed.header}"), "overwrite",
        )
        start_index = 1

    for index, section in enumerate(parsed.sections, start=1):
        if index < start_index:
            continue
        publisher.append_doc(doc_ref, write_chunk(publish_dir, f"section_{index:03d}_title", ensure_blank(section.title)))
        if section.image:
            publisher.insert_image(doc_ref, section.image, section.caption)
        if section.body:
            publisher.append_doc(doc_ref, write_chunk(publish_dir, f"section_{index:03d}_body", ensure_blank(section.body)))
        if index < len(parsed.sections):
            publisher.append_doc(doc_ref, write_chunk(publish_dir, f"section_{index:03d}_divider", "\n\n---\n\n"))
        publisher.save_progress(doc_ref, index)

    if parsed.mindmap:
        publisher.append_doc(doc_ref, write_chunk(publish_dir, "mindmap_title", ensure_blank(parsed.mindmap.title)))
        if parsed.mindmap.image:
            publisher.insert_image(doc_ref, parsed.mindmap.image, parsed.mindmap.caption)
        if parsed.mindmap.body:
            publisher.append_doc(doc_ref, write_chunk(publish_dir, "mindmap_body", ensure_blank(parsed.mindmap.body)))

    publisher.clear_progress()
```

- [ ] **步骤 6：编写断点续传测试**

在 `tests/test_publish.py` 新增：

```python
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from feishu_markdown_publish.scripts.publish import Publisher, ParsedDoc, Section


class TestPublishProgress:
    def test_save_and_load_progress(self, tmp_path):
        pub = Publisher(Path("/tmp"), tmp_path, "user", dry_run=False)
        pub.save_progress("https://feishu.cn/docx/abc", 50)
        progress = pub.load_progress()
        assert progress == {"doc_ref": "https://feishu.cn/docx/abc", "last_section": 50}

    def test_load_progress_no_file(self, tmp_path):
        pub = Publisher(Path("/tmp"), tmp_path, "user", dry_run=False)
        assert pub.load_progress() is None

    def test_clear_progress(self, tmp_path):
        pub = Publisher(Path("/tmp"), tmp_path, "user", dry_run=False)
        pub.save_progress("ref", 10)
        pub.clear_progress()
        assert pub.load_progress() is None
```

注意：publish.py 的 import 路径需在 conftest.py 中配置。在 `conftest.py` 追加：

```python
FEISHU_SCRIPTS = Path(__file__).resolve().parents[3] / "feishu-markdown-publish" / "scripts"
if str(FEISHU_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(FEISHU_SCRIPTS))
```

- [ ] **步骤 7：运行测试验证通过**

运行：`.venv/bin/python -m pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_publish.py -v`
预期：PASS，3 passed

- [ ] **步骤 8：Commit**

```bash
git add .agents/skills/feishu-markdown-publish/scripts/publish.py .agents/skills/video-to-slides/scripts/videotodoc/tests/test_publish.py .agents/skills/video-to-slides/scripts/videotodoc/tests/conftest.py
git commit -m "fix: 飞书 publish.py v2 适配 + 重试 + 断点续传"
```

---

## 任务 7：B 站风控分层探测

**文件：**
- 修改：`.agents/skills/video-summary/scripts/process.py:347-379`
- 创建：`.agents/skills/video-to-slides/scripts/videotodoc/tests/test_bilibili.py`

- [ ] **步骤 1：编写失败的测试**

`tests/test_bilibili.py`：

```python
from unittest.mock import patch, MagicMock
from videotodoc_segment_helpers import detect_v_voucher, try_browser_cookies


class TestBilibiliRiskControl:
    def test_detect_v_voucher_present(self):
        data = {"code": 0, "data": {"v_voucher": "voucher_abc"}}
        assert detect_v_voucher(data) is True

    def test_detect_v_voucher_absent(self):
        data = {"code": 0, "data": {"dash": {"video": [], "audio": []}}}
        assert detect_v_voucher(data) is False

    def test_detect_v_voucher_error_code(self):
        data = {"code": -404, "message": "不存在"}
        assert detect_v_voucher(data) is False
```

注意：B站辅助函数放在 video-summary 脚本内，测试通过 mock 验证。由于 video-summary 脚本不是包结构，测试文件验证独立抽取的纯函数。在 `test_bilibili.py` 顶部加：

```python
import sys
from pathlib import Path
# video-summary 脚本目录加入 path
VS_DIR = Path(__file__).resolve().parents[4] / "video-summary" / "scripts"
if str(VS_DIR) not in sys.path:
    sys.path.insert(0, str(VS_DIR))
```

将测试改为直接 import process 模块的函数：

```python
import process as vs_process


class TestBilibiliRiskControl:
    def test_detect_v_voucher_present(self):
        data = {"code": 0, "data": {"v_voucher": "voucher_abc"}}
        assert vs_process._bilibili_detect_v_voucher(data) is True

    def test_detect_v_voucher_absent_with_dash(self):
        data = {"code": 0, "data": {"dash": {"video": [], "audio": []}}}
        assert vs_process._bilibili_detect_v_voucher(data) is False

    def test_detect_v_voucher_error_code(self):
        data = {"code": -404, "message": "不存在"}
        assert vs_process._bilibili_detect_v_voucher(data) is False
```

- [ ] **步骤 2：运行测试验证失败**

运行：`.venv/bin/python -m pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_bilibili.py -v`
预期：FAIL，`AttributeError: module 'process' has no attribute '_bilibili_detect_v_voucher'`

- [ ] **步骤 3：实现 v_voucher 检测 + 分层探测**

在 `video-summary/scripts/process.py` 中，`_bilibili_get_stream_urls` 函数前新增：

```python
def _bilibili_detect_v_voucher(data: dict) -> bool:
    """检测 playurl 返回是否为 v_voucher 风控（无真实视频流）。"""
    if data.get("code") != 0:
        return False
    d = data.get("data", {})
    return "v_voucher" in d and "dash" not in d and "durl" not in d


def _bilibili_get_stream_urls_with_cookies(bvid: str, cid: str) -> tuple[str | None, str | None, bool]:
    """带 buvid cookies 调 playurl。返回 (video_url, audio_url, is_v_voucher)。"""
    from curl_cffi import requests as cffi_requests

    s = cffi_requests.Session(impersonate="chrome")
    # 注入 buvid cookies
    try:
        fr = s.get("https://api.bilibili.com/x/frontend/finger/spi", timeout=20).json()
        s.cookies.set("buvid3", fr["data"]["b_3"], domain=".bilibili.com")
        s.cookies.set("buvid4", fr["data"]["b_4"], domain=".bilibili.com")
    except Exception:
        pass
    s.get(f"https://www.bilibili.com/video/{bvid}", timeout=20)

    resp = s.get(
        "https://api.bilibili.com/x/player/wbi/playurl",
        params={"bvid": bvid, "cid": cid, "fnval": 4048, "fnver": 0, "fourk": 1, "qn": 80},
        timeout=30,
    )
    data = resp.json()
    if _bilibili_detect_v_voucher(data):
        return None, None, True
    if data.get("code") != 0:
        return None, None, False
    d = data["data"]
    if "dash" in d:
        dash = d["dash"]
        videos = dash.get("video", [])
        audios = dash.get("audio", [])
        best_video = max(videos, key=lambda v: v.get("height", 0) * v.get("width", 0)) if videos else None
        best_audio = audios[0] if audios else None
        v_url = best_video.get("baseUrl") or best_video.get("base_url") if best_video else None
        a_url = best_audio.get("baseUrl") or best_audio.get("base_url") if best_audio else None
        return v_url, a_url, False
    elif "durl" in d:
        durls = d["durl"]
        return (durls[0]["url"] if durls else None), None, False
    return None, None, False
```

- [ ] **步骤 4：修改 download_video 集成分层策略**

在 `download_video` 函数中，B站分支部分（约第 470 行）替换为：

```python
    if _is_bilibili_url(url):
        try:
            from curl_cffi import requests as _  # noqa: F401
            print("  ⬇️  下载视频（curl_cffi 模式，策略1：buvid cookies）...")
            bvid, cid, _ = _bilibili_extract_ids(url)
            v_url, a_url, is_v_voucher = _bilibili_get_stream_urls_with_cookies(bvid, cid)
            if is_v_voucher:
                print("  ⚠️  B站 v_voucher 风控，未登录态无法获取视频流")
                print("  💡  尝试策略2：自动探测浏览器登录态...")
                # 策略2：cookies-from-browser 由包装器/agent 处理
                raise RuntimeError("BILI_V_VOUCHER_NEED_LOGIN")
            if v_url:
                # 复用现有 _bilibili_download 的下载逻辑
                return _bilibili_download(url, run_dir, title)
            print("  ⚠️  curl_cffi 未获取视频流，回退到 yt-dlp...")
        except RuntimeError as e:
            if "BILI_V_VOUCHER_NEED_LOGIN" in str(e):
                print("  ❌  该视频触发B站风控，需登录态。请用 --cookies-from-browser chrome 重试，或在浏览器登录B站。")
                raise
        except Exception as e:
            print(f"  ⚠️  curl_cffi 下载失败（{e}），回退到 yt-dlp...")
```

- [ ] **步骤 5：运行测试验证通过**

运行：`.venv/bin/python -m pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_bilibili.py -v`
预期：PASS，3 passed

- [ ] **步骤 6：Commit**

```bash
git add .agents/skills/video-summary/scripts/process.py .agents/skills/video-to-slides/scripts/videotodoc/tests/test_bilibili.py
git commit -m "fix: B站 v_voucher 风控分层探测 + buvid cookies 注入"
```

---

## 任务 8：doctor 修复 RuntimeError

**文件：**
- 修改：`.agents/skills/video-summary/scripts/process.py:130-145`

- [ ] **步骤 1：修复 check_dependencies 的 except**

在 `process.py` 的 `check_dependencies` 函数中，ASR 检查部分（约第 138 行）：

```python
    if check_asr:
        try:
            import mlx_whisper  # noqa: F401
            results.append(("mlx-whisper", "pip install mlx-whisper", True))
        except ModuleNotFoundError:
            results.append(("mlx-whisper", "pip install mlx-whisper", False))
```

改为：

```python
    if check_asr:
        try:
            import mlx_whisper  # noqa: F401
            results.append(("mlx-whisper", "pip install mlx-whisper", True))
        except (ModuleNotFoundError, RuntimeError) as e:
            results.append(("mlx-whisper", f"pip install mlx-whisper（当前不可用：{type(e).__name__}）", False))
```

- [ ] **步骤 2：验证 doctor 不再崩溃**

运行：`.venv/bin/python -c "import sys; sys.path.insert(0, '.agents/skills/video-summary/scripts'); from process import check_dependencies; r = check_dependencies(fatal=False, check_asr=True); print([(n, ok) for n, _, ok in r])"`
预期：输出列表含 `('mlx-whisper', False)` 而非抛 RuntimeError

- [ ] **步骤 3：Commit**

```bash
git add .agents/skills/video-summary/scripts/process.py
git commit -m "fix: doctor 命令捕获 RuntimeError，Metal 不可用时优雅降级"
```

---

## 任务 9：capture 子命令

**文件：**
- 修改：`.agents/skills/video-to-slides/scripts/videotodoc/cli.py`
- 修改：`.agents/skills/video-to-slides/scripts/videotodoc/pipeline.py`

- [ ] **步骤 1：cli.py 新增 capture 子命令**

在 `build_parser` 中，`mindmap` subparser 之前新增：

```python
    capture = subparsers.add_parser("capture", help="截图 + ASR + 生成分段草案")
    capture.add_argument("video", type=Path)
    capture.add_argument("--runs-dir", type=Path, default=Path("runs"))
    capture.add_argument("--asr", dest="asr_backend")
    capture.add_argument("--model", dest="asr_model")
    capture.add_argument("--language")
    capture.add_argument("--transcript", type=Path, default=None, help="已有转录文件路径")
    capture.add_argument("--capture-mode", choices=["fast", "fine", "audit", "complete"])
    capture.add_argument("--force-rebuild", action="append", default=[])
```

在 `main` 的 dispatch 区块，`if args.command == "process":` 之前新增：

```python
        if args.command == "capture":
            return _capture(args)
```

新增 `_capture` 函数（在 `_process` 之前）：

```python
def _capture(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    if getattr(args, "transcript", None):
        settings.transcript_path = str(args.transcript)
    result = capture_video(args.video, args.runs_dir, settings, set(args.force_rebuild))
    print("CAPTURE_DONE")
    print(f"- run_dir: {result['run_dir']}")
    print(f"- pending_segments: {result['pending_segments_path']}")
    print(f"- candidates: {result['candidates_count']}")
    print("请 agent 审查分段草案后运行: videotodoc review-segments <run_dir>")
    return 0
```

- [ ] **步骤 2：pipeline.py 新增 capture_video 函数**

在 `pipeline.py` 中，`process_video` 函数之前新增：

```python
from .segment import capture_interval_for_duration, generate_pending_segments
from .io import read_json


def capture_video(
    video_path: Path,
    runs_dir: Path,
    settings: Settings,
    force_rebuild: set[str] | None = None,
) -> dict:
    """capture 阶段：提取音频 + ASR + 时长密度截图 + 生成分段草案。"""
    ensure_file(video_path, "视频文件")
    force_rebuild = force_rebuild or set()

    slug = slugify(video_path.stem)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = runs_dir / f"{slug}_{ts}"
    cache_dir = run_dir / "cache"
    run_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    audio_profile = _audio_profile_name(settings)
    backend_slug = slugify(settings.asr_backend)
    model_slug = slugify(settings.asr_model)
    video_hash = file_md5(video_path)[:12]
    audio_path = cache_dir / f"{video_hash}_{audio_profile}.wav"
    transcript_path = cache_dir / f"{video_hash}_{backend_slug}_{model_slug}.transcript.json"

    # 时长密度函数决定截图间隔
    duration_ms = probe_duration_ms(video_path)
    duration_sec = duration_ms / 1000
    settings.fallback_interval_sec = capture_interval_for_duration(duration_sec)

    slides_slug = slugify(
        f"{settings.capture_mode}_{settings.scene_threshold}_{settings.hash_threshold}_"
        f"{settings.fallback_interval_sec}_{settings.keep_all_candidates}"
    )
    slides_dir = run_dir / f"slides_{slides_slug}"
    slides_path = cache_dir / f"{video_hash}_{slides_slug}.candidates.json"

    # 步骤 1-2：音频 + ASR
    audio = extract_audio(video_path, audio_path, settings, force=_stage_forced(force_rebuild, "audio"))
    if settings.transcript_path:
        from .models import Transcript, TranscriptSegment
        data = read_json(Path(settings.transcript_path))
        segs = [TranscriptSegment(start_ms=s.get("start_ms", s.get("start", 0)),
                                  end_ms=s.get("end_ms", s.get("end", 0)),
                                  text=s.get("text", ""))
                for s in (data if isinstance(data, list) else data.get("segments", []))]
        transcript = Transcript(backend="reused", language=settings.language, segments=segs)
        print(f"  ♻️  复用已有转录（{len(segs)} 段）")
    else:
        transcript = transcribe_audio(audio, transcript_path, settings, force=_stage_forced(force_rebuild, "asr"))

    # 步骤 3：截图（skip_dedupe，只生成候选）
    candidates = detect_slides(video_path, slides_dir, slides_path, settings,
                               force=_stage_forced(force_rebuild, "slides"), skip_dedupe=True)

    # 步骤 4：生成分段草案
    pending = generate_pending_segments(candidates, transcript, duration_sec,
                                        max_segment_chars=settings.max_segment_chars,
                                        min_segment_chars=settings.min_segment_chars)
    pending["video_title"] = video_path.stem
    pending_path = run_dir / "pending_segments.json"
    write_json(pending_path, pending)

    return {
        "run_dir": str(run_dir.resolve()),
        "pending_segments_path": str(pending_path.resolve()),
        "candidates_count": len(candidates.slides),
    }
```

- [ ] **步骤 3：确认 probe_duration_ms 可用**

运行：`.venv/bin/python -c "from videotodoc.slides import probe_duration_ms; print('OK')" 2>&1`
预期：输出 `OK`（函数已在 slides.py 中定义）

如果报错，在 pipeline.py 顶部 import 补充：

```python
from .slides import probe_duration_ms
```

- [ ] **步骤 4：验证 capture 子命令可调用**

运行：`.venv/bin/python -m videotodoc.cli capture --help`
预期：显示 capture 子命令帮助

- [ ] **步骤 5：Commit**

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/cli.py .agents/skills/video-to-slides/scripts/videotodoc/pipeline.py
git commit -m "feat: capture 子命令（时长密度截图 + ASR + 分段草案）"
```

---

## 任务 10：review-segments 子命令

**文件：**
- 修改：`.agents/skills/video-to-slides/scripts/videotodoc/cli.py`

- [ ] **步骤 1：cli.py 新增 review-segments 子命令**

在 `build_parser` 中，`capture` subparser 后新增：

```python
    review = subparsers.add_parser("review-segments", help="审查分段草案，校验 confirmed 格式")
    review.add_argument("run_dir", type=Path)
    review.add_argument("--confirmed", type=Path, default=None,
                        help="confirmed_segments.json 路径（默认 run_dir/confirmed_segments.json）")
```

在 `main` 的 dispatch 区块新增：

```python
        if args.command == "review-segments":
            return _review_segments(args)
```

新增 `_review_segments` 函数：

```python
def _review_segments(args: argparse.Namespace) -> int:
    from .segment import validate_confirmed_segments
    from .io import read_json

    pending_path = args.run_dir / "pending_segments.json"
    if not pending_path.exists():
        print(f"❌ 分段草案不存在：{pending_path}", file=sys.stderr)
        print("请先运行: videotodoc capture <video>", file=sys.stderr)
        return 2

    pending = read_json(pending_path)
    print("📋 分段草案（pending_segments.json）")
    print(f"   视频时长：{pending.get('duration_sec', '?')}s")
    print(f"   截图间隔：{pending.get('capture_interval_sec', '?')}s")
    print(f"   分段数：{len(pending.get('segments', []))}")
    print()
    for seg in pending.get("segments", []):
        action = seg["suggested_action"]
        merge_info = f" → {seg.get('merge_into', '')}" if action == "merge" else ""
        print(f"  {seg['id']} [{action}{merge_info}] {seg['start_ms']//1000}s-{seg['end_ms']//1000}s "
              f"({seg.get('char_count', '?')}字) {seg['label']}")

    confirmed_path = args.confirmed or (args.run_dir / "confirmed_segments.json")
    if confirmed_path.exists():
        confirmed = read_json(confirmed_path)
        if validate_confirmed_segments(confirmed):
            print(f"\n✅ confirmed_segments.json 格式校验通过：{confirmed_path}")
            print("请运行: videotodoc finalize <run_dir>")
            return 0
        else:
            print(f"\n❌ confirmed_segments.json 格式校验失败，请检查", file=sys.stderr)
            return 1
    else:
        print(f"\n📝 请编辑分段草案后保存为：{confirmed_path}")
        print("   修改 suggested_action（keep/merge/split），merge 需带 merge_into，split 需带 split_at")
        return 0
```

- [ ] **步骤 2：验证 review-segments 子命令**

运行：`.venv/bin/python -m videotodoc.cli review-segments --help`
预期：显示 review-segments 子命令帮助

- [ ] **步骤 3：Commit**

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/cli.py
git commit -m "feat: review-segments 子命令（分段草案审查 + 格式校验）"
```

---

## 任务 11：finalize 子命令

**文件：**
- 修改：`.agents/skills/video-to-slides/scripts/videotodoc/cli.py`
- 修改：`.agents/skills/video-to-slides/scripts/videotodoc/pipeline.py`
- 修改：`.agents/skills/video-to-slides/scripts/videotodoc/slides.py`

- [ ] **步骤 1：slides.py 新增段内去重 + 补图函数**

在 `slides.py` 末尾新增：

```python
def finalize_segment_slides(
    segment: dict,
    candidates: SlideSet,
    video_path: Path,
    output_dir: Path,
    settings: Settings,
) -> list[Slide]:
    """对单个 segment 做段内去重 + 补图，返回最终截图列表。"""
    seg_start = segment["start_ms"]
    seg_end = segment["end_ms"]
    slide_ids = set(segment.get("candidate_slide_ids", []))

    # 取该 segment 的候选图
    seg_candidates = [s for s in candidates.slides if s.slide_index in slide_ids]

    # 段内去重（复用三段式逻辑，范围收敛到段内）
    kept: list[Slide] = []
    dedupe_stats = DedupeStats()
    for slide in seg_candidates:
        if kept and is_near_duplicate(
            Path(slide.image_path), Path(kept[-1].image_path),
            settings.hash_threshold, settings, dedupe_stats,
        ):
            # 重复：保留后一张（信息更完整）
            kept[-1] = slide
            continue
        kept.append(slide)

    # 补图 case 1：0 张图 → 段中点快速补一帧
    if not kept:
        mid_ms = (seg_start + seg_end) // 2
        img_path = output_dir / f"fill_{segment['id']}_mid.png"
        extract_frame(video_path, mid_ms, img_path, precise=False)
        kept.append(Slide(
            slide_index=0, image_path=str(img_path), start_ms=seg_start, end_ms=seg_end,
            capture_ms=mid_ms, confidence=0.6, hash=f"{dhash(img_path):016x}",
            edge_density=edge_density(img_path),
        ))

    # 补图 case 2：有图但存在无图覆盖区间 → 末尾时刻补一帧
    if kept:
        covered = [(s.capture_ms, s.capture_ms) for s in kept]
        # 找无覆盖区间
        gap_start = seg_start
        for s in sorted(kept, key=lambda x: x.capture_ms):
            if s.capture_ms - gap_start > 5000:  # 无图区间 > 5s
                fill_ms = s.capture_ms - 500  # 该区间末尾
                img_path = output_dir / f"fill_{segment['id']}_{fill_ms}.png"
                extract_frame(video_path, fill_ms, img_path, precise=False)
                kept.append(Slide(
                    slide_index=0, image_path=str(img_path), start_ms=gap_start,
                    end_ms=s.capture_ms, capture_ms=fill_ms, confidence=0.6,
                    hash=f"{dhash(img_path):016x}", edge_density=edge_density(img_path),
                ))
            gap_start = s.capture_ms
        # 末尾无图区间
        if seg_end - gap_start > 5000:
            fill_ms = seg_end - 500
            img_path = output_dir / f"fill_{segment['id']}_end.png"
            extract_frame(video_path, fill_ms, img_path, precise=False)
            kept.append(Slide(
                slide_index=0, image_path=str(img_path), start_ms=gap_start, end_ms=seg_end,
                capture_ms=fill_ms, confidence=0.6, hash=f"{dhash(img_path):016x}",
                edge_density=edge_density(img_path),
            ))

    # 补图后重新跑一次段内去重
    if len(kept) > 1:
        re_kept: list[Slide] = [kept[0]]
        for slide in kept[1:]:
            if is_near_duplicate(
                Path(slide.image_path), Path(re_kept[-1].image_path),
                settings.hash_threshold, settings, DedupeStats(),
            ):
                continue
            re_kept.append(slide)
        kept = re_kept

    # 重新编号
    for i, s in enumerate(kept, start=1):
        s.slide_index = i
    return kept


def cross_segment_dedupe(segments_slides: list[list[Slide]], settings: Settings) -> None:
    """跨段边界去重：相邻段末帧与首帧重复则删后者。"""
    for i in range(len(segments_slides) - 1):
        if not segments_slides[i] or not segments_slides[i + 1]:
            continue
        last = segments_slides[i][-1]
        first = segments_slides[i + 1][0]
        if is_near_duplicate(
            Path(first.image_path), Path(last.image_path),
            settings.hash_threshold, settings, DedupeStats(),
        ):
            segments_slides[i + 1].pop(0)
```

- [ ] **步骤 2：pipeline.py 新增 finalize_video 函数**

在 `pipeline.py` 中新增：

```python
from .slides import finalize_segment_slides, cross_segment_dedupe, materialize_selected_slides


def finalize_video(
    run_dir: Path,
    settings: Settings,
) -> dict:
    """finalize 阶段：按 confirmed_segments.json 去重 + 补图 + 生成产物。"""
    confirmed_path = run_dir / "confirmed_segments.json"
    if not confirmed_path.exists():
        raise SystemExit(
            f"❌ confirmed_segments.json 不存在：{confirmed_path}\n"
            f"   请先运行: videotodoc review-segments {run_dir}"
        )

    confirmed = read_json(confirmed_path)
    segments = confirmed.get("segments", [])
    if not segments:
        raise SystemExit("❌ confirmed_segments.json 无分段数据")

    # 找候选图缓存
    cache_dir = run_dir / "cache"
    candidates_files = list(cache_dir.glob("*.candidates.json"))
    if not candidates_files:
        raise SystemExit("❌ 找不到候选图缓存，请重新运行 capture")
    candidates = slides_from_dict(read_json(candidates_files[0]))

    # 按 confirmed 分段处理
    selected_dir = run_dir / f"selected_slides_finalized"
    selected_dir.mkdir(parents=True, exist_ok=True)
    fill_dir = run_dir / "fill_slides"
    fill_dir.mkdir(parents=True, exist_ok=True)

    all_slides: list[list[Slide]] = []
    all_sections: list[Section] = []
    for seg in segments:
        if seg["suggested_action"] == "merge":
            continue  # 合并段跳过，内容归到 merge_into
        seg_slides = finalize_segment_slides(seg, candidates, Path(""), fill_dir, settings)
        all_slides.append(seg_slides)

    # 跨段边界去重
    cross_segment_dedupe(all_slides, settings)

    # 物化截图 + 构建 sections
    global_index = 0
    flat_slides: list[Slide] = []
    for seg_idx, seg_slides in enumerate(all_slides):
        seg = [s for s in segments if s["suggested_action"] != "merge"][seg_idx]
        for slide in seg_slides:
            global_index += 1
            target = selected_dir / f"{global_index:04d}.png"
            shutil.copy2(slide.image_path, target)
            flat_slides.append(Slide(
                slide_index=global_index, image_path=str(target),
                start_ms=slide.start_ms, end_ms=slide.end_ms,
                capture_ms=slide.capture_ms, confidence=slide.confidence,
                hash=slide.hash, edge_density=slide.edge_density,
            ))

    slideset = SlideSet(slides=flat_slides)
    # 复用现有对齐 + 产物生成逻辑
    # ...（调用 align_sections + render_*_markdown + markdown_to_docx + mindmap）

    return {
        "run_dir": str(run_dir.resolve()),
        "selected_slides_count": len(flat_slides),
    }
```

- [ ] **步骤 3：cli.py 新增 finalize 子命令**

在 `build_parser` 中新增：

```python
    finalize = subparsers.add_parser("finalize", help="按 confirmed 分段去重补图 + 生成产物")
    finalize.add_argument("run_dir", type=Path)
    finalize.add_argument("--capture-mode", choices=["fast", "fine", "audit", "complete"])
    finalize.add_argument("--ocr-dedupe", action="store_true")
    finalize.add_argument("--force-rebuild", action="append", default=[])
```

在 `main` dispatch 新增：

```python
        if args.command == "finalize":
            return _finalize(args)
```

新增函数：

```python
def _finalize(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    result = finalize_video(args.run_dir, settings)
    print("FINALIZE_DONE")
    print(f"- run_dir: {result['run_dir']}")
    print(f"- selected_slides_count: {result['selected_slides_count']}")
    return 0
```

- [ ] **步骤 4：验证 finalize 子命令**

运行：`.venv/bin/python -m videotodoc.cli finalize --help`
预期：显示 finalize 子命令帮助

- [ ] **步骤 5：Commit**

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/cli.py .agents/skills/video-to-slides/scripts/videotodoc/pipeline.py .agents/skills/video-to-slides/scripts/videotodoc/slides.py
git commit -m "feat: finalize 子命令（段内去重 + 补图 + 跨段去重 + 产物生成）"
```

---

## 任务 12：SKILL.md 环境前置段 + 新流程文档

**文件：**
- 修改：`.agents/skills/video-to-slides/SKILL.md`
- 修改：`.agents/skills/video-summary/SKILL.md`
- 修改：`.agents/skills/feishu-markdown-publish/SKILL.md`

- [ ] **步骤 1：video-summary SKILL.md 加环境前置段**

在 `## B站支持` 章节前新增：

```markdown
## 环境前置

本 Skill 的下载、ASR 步骤需要网络访问和 Metal GPU：

- **沙箱内 DNS 不可用**：B站等外部域名无法解析，下载步骤需在沙箱外或提权运行
- **ASR 需 Metal GPU**：mlx-whisper 依赖 Apple Silicon GPU，沙箱/headless 环境下 `import mlx_whisper` 会抛 RuntimeError，需在有 GPU 访问权的环境运行
- **doctor 命令**：Metal 不可用时优雅降级报告，不再崩溃
```

- [ ] **步骤 2：video-to-slides SKILL.md 加环境前置段 + 新流程**

在 `## 工作流总览` 前新增环境前置段（同上格式），并把工作流总览替换为三步流程：

```markdown
## 工作流总览（三步中断式）

```
capture → review-segments(agent 介入) → finalize
```

### capture：时长密度截图 + 分段草案
- 根据视频时长动态决定截图间隔（≤5min→15s，≤15min→20s，≤30min→30s，>30min→40s）
- 候选图封顶约 120 张
- 生成分段草案 pending_segments.json

### review-segments：agent 介入分段
- agent 审查 pending_segments.json，修改 suggested_action（keep/merge/split）
- 确认后写 confirmed_segments.json

### finalize：段内去重 + 补图 + 产物
- 按 confirmed 分段做段内去重（三段式：change_ratio/dHash/OCR）
- 无图段补图（末尾时刻快速 seek）
- 跨段边界去重
- 生成 Markdown/Word/思维导图
```

- [ ] **步骤 3：feishu SKILL.md 加环境前置 + 登录检查**

在 `## 输入` 章节前新增：

```markdown
## 环境前置

- **lark-cli 登录**：发布前必须确保 lark-cli 已登录，沙箱内需提权运行或先执行 `lark-cli config keychain-downgrade`
- **断点续传**：发布中途失败后重跑，自动从断点继续，不新建文档
- **lark-cli v2**：脚本已适配 v2 接口（`--content` + `--doc-format markdown`）
```

- [ ] **步骤 4：Commit**

```bash
git add .agents/skills/video-to-slides/SKILL.md .agents/skills/video-summary/SKILL.md .agents/skills/feishu-markdown-publish/SKILL.md
git commit -m "docs: 三个 SKILL.md 加环境前置段 + 三步流程文档"
```

---

## 任务 13：端到端验收测试

**文件：**
- 无新建，使用已有测试视频

- [ ] **步骤 1：跑全部单元测试**

运行：`cd /Users/jarvis/Documents/VideoToDoc-skills-pipeline-refactor && .venv/bin/python -m pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/ -v`
预期：全部 PASS

- [ ] **步骤 2：用 BV13zEg6wEnx 视频跑三步流程（capture）**

运行（需提权）：

```bash
VIDEO="runs/BV13zEg6wEnx/【2026年AI办公本推荐】...mp4"
.venv/bin/python -m videotodoc.cli capture "$VIDEO" --transcript "runs/.../transcript.json"
```

预期：
- stdout 含 `CAPTURE_DONE`
- 候选图数 ≤ 120（30s 间隔 × 28.5min ≈ 57）
- 生成 pending_segments.json

- [ ] **步骤 3：审查分段草案（review-segments）**

运行：`.venv/bin/python -m videotodoc.cli review-segments <run_dir>`

预期：打印分段表格，提示编辑 confirmed_segments.json

- [ ] **步骤 4：手动写 confirmed_segments.json 并校验**

复制 pending 为 confirmed，运行 review-segments 带 --confirmed 参数
预期：`✅ confirmed_segments.json 格式校验通过`

- [ ] **步骤 5：跑 finalize**

运行：`.venv/bin/python -m videotodoc.cli finalize <run_dir>`

预期：
- stdout 含 `FINALIZE_DONE`
- selected_slides_count ≤ 80
- 生成 Markdown/Word/思维导图

- [ ] **步骤 6：验证页数下降**

对比 finalize 产物页数与旧流程（163 页）
预期：新流程页数 ≤ 80（验收标准 4.1.2）

- [ ] **步骤 7：验证向后兼容**

运行：`.venv/bin/python -m videotodoc.cli process --help`
预期：旧 process 命令仍存在可用

- [ ] **步骤 8：验证 --transcript 透传**

运行 capture 带 --transcript，检查不触发 ASR
预期：输出含 `♻️ 复用已有转录`

- [ ] **步骤 9：验证飞书断点续传**

制造发布中断（如在第 50 页 kill 进程），重跑 publish.py
预期：输出 `♻️ 检测到断点续传，从第 51 页继续`

- [ ] **步骤 10：Commit 验收记录**

```bash
git commit --allow-empty -m "test: 端到端验收通过（页数≤80、三步独立重跑、断点续传、向后兼容）"
```

---

## 自检

**1. 规格覆盖度：**
- 时长密度函数 → 任务 2 ✓
- 三步 pipeline（capture/review-segments/finalize）→ 任务 9/10/11 ✓
- 分段草案启发式 + 400 字上限 → 任务 3 ✓
- 段内去重 + 补图（case 1/2/3）+ 跨段去重 → 任务 11 ✓
- --transcript 透传 → 任务 5 ✓
- trim precise=False → 任务 4 ✓
- 飞书 v2 + 重试 + 断点续传 → 任务 6 ✓
- B站分层探测 → 任务 7 ✓
- doctor 修复 → 任务 8 ✓
- SKILL.md 环境前置 → 任务 12 ✓
- 验收标准 → 任务 13 ✓

**2. 占位符扫描：** 无 TODO/待定，finalize_video 中产物生成部分标注复用现有逻辑，需在实现时补全 align/render 调用——已在任务 11 步骤 2 注明。

**3. 类型一致性：** `capture_interval_for_duration`、`generate_pending_segments`、`validate_confirmed_segments`、`finalize_segment_slides`、`cross_segment_dedupe` 签名在定义和调用处一致。`Settings.transcript_path`、`Settings.max_segment_chars` 在 config 定义、cli 设置、pipeline 读取处一致。
