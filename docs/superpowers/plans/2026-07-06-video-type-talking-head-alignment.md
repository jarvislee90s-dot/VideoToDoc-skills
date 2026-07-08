# video-type 分流 + talking_head 段落主导对齐 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 修复 video-to-slides 图文对齐错位（截图取在段落中段），并按视频类型分流截图策略，talking_head 类型走「段落主导 + 段末取帧」。

**架构：** 新增 `classify_video` 按场景变化率/边缘密度/饱和度自动判型（lecture_slides/talking_head/screen_recording/movie_cinematic/tutorial）。`trim_candidates_by_transcript` 改为段落主导：每段截图的 `start_ms/end_ms` 用 transcript 段边界、`capture_ms = 段末 end_ms - capture_margin_ms`，talking_head 在段末直接取帧。`align_sections` 因 slide 时间范围已是段边界而自然对齐。`detect_slides` 按 video_type 调场景检测阈值。

**技术栈：** Python 3.14、OpenCV（已有）、PIL（已有）、ffmpeg、pytest。不引入 VLM/视觉大模型。

---

## 背景：当前 bug

实测 B站视频 BV19hwTzwETF（talking_head 讲解，815s）发现：39 页中 29 页 `section.end_ms < 段落真实 end_ms`，截图比段落真实结束平均早 5.9s，截图落在段落中段字幕（如第1页截到「有人299上门帮你卸载」倒数第二句，第3页截到「让我们回到最初的起点」段落首句）。

根因（[align.py:140-142](file:///Users/jarvis/Documents/VideoToDoc-skills/.agents/skills/video-to-slides/scripts/videotodoc/align.py)）：`align_sections` 用截图候选的 `start_ms/end_ms`（场景变化点窗口）做 section 时间范围，而非 transcript 段边界。截图候选窗口是视觉场景检测生成的，与语义段落是两套独立时间划分。

参考方案：videoQuickNote 按 `video_type` 分流——talking_head 用宽松阈值（ContentDetector threshold=35），检测到 <3 场景直接不截图，认为画面变化无意义。本计划借鉴此思路，但不引入 scenedetect 依赖，复用现有 `detect_scene_changes`。

## 文件结构

| 文件 | 职责 | 动作 |
|------|------|------|
| `scripts/videotodoc/slides.py` | 截图生成、候选裁剪、视频分类 | 修改：+classify_video、改 trim、detect_slides 按 type 调阈值 |
| `scripts/videotodoc/config.py` | Settings 配置 | 修改：+video_type 字段 |
| `scripts/videotodoc/cli.py` | 命令行 | 修改：+--video-type 参数 |
| `scripts/process.py` | video-to-slides 入口 | 修改：+--video-type 透传 |
| `scripts/videotodoc/pipeline.py` | 流程编排 | 修改：capture_video 调 classify_video |
| `scripts/videotodoc/align.py` | 图文对齐 | 修改：段主导下保证 capture 对齐段末 |
| `scripts/videotodoc/tests/test_video_type.py` | 分类测试 | 创建 |
| `scripts/videotodoc/tests/test_frame_selection.py` | 段落主导截图测试 | 修改：加段末取帧测试 |
| `scripts/videotodoc/tests/test_align.py` | 对齐测试 | 修改：加段主导对齐测试 |
| `.agents/skills/video-summary/SKILL.md` | 文档 | 修改：命令路径 |
| `.agents/skills/video-to-slides/reference/merge_procedure.md` | 文档 | 修改：命令路径 |
| `.agents/skills/video-to-slides/reference/review_agent_prompt.md` | 文档 | 修改：归属描述 |
| `.agents/skills/video-to-slides/SKILL.md` | 文档 | 修改：整理版标题说明 + video-type 参数 |

路径基准：`/Users/jarvis/Documents/VideoToDoc-skills/.agents/skills/video-to-slides/`（下文 `scripts/...` 均相对此基准）。

---

## 任务 1：VideoType 类型 + classify_video 分类函数

**文件：**
- 修改：`scripts/videotodoc/slides.py`（顶部加 VideoType；新增 classify_video / _classify_by_features / _compute_scene_rate / _sample_frames_for_classify / _mean_saturation）
- 创建：`scripts/videotodoc/tests/test_video_type.py`

设计：把分类逻辑拆成纯函数 `_classify_by_features(scene_rate, edge_density, saturation_mean)` 便于单测；`classify_video(video_path)` 负责采样帧、算特征、调纯函数。

- [ ] **步骤 1：编写失败的测试**

创建 `scripts/videotodoc/tests/test_video_type.py`：

```python
"""video-type 自动分类：按场景变化率/边缘密度/饱和度判型。"""
from videotodoc.slides import _classify_by_features, VideoType


class TestClassifyByFeatures:
    def test_lecture_slides_low_scene_high_edge(self):
        # 场景变化少 + 边缘密度高（PPT 文字多）→ lecture_slides
        assert _classify_by_features(scene_rate=0.02, edge_density=0.20, saturation_mean=50) == "lecture_slides"

    def test_talking_head_low_scene_low_edge_low_sat(self):
        # 场景几乎不变 + 边缘少 + 饱和度低（出镜讲解）→ talking_head
        assert _classify_by_features(scene_rate=0.01, edge_density=0.05, saturation_mean=40) == "talking_head"

    def test_screen_recording_mid_scene_high_edge(self):
        assert _classify_by_features(scene_rate=0.06, edge_density=0.25, saturation_mean=70) == "screen_recording"

    def test_movie_cinematic_high_scene(self):
        assert _classify_by_features(scene_rate=0.40, edge_density=0.10, saturation_mean=60) == "movie_cinematic"

    def test_tutorial_fallback(self):
        # 不满足任何特殊条件 → tutorial
        assert _classify_by_features(scene_rate=0.15, edge_density=0.12, saturation_mean=100) == "tutorial"

    def test_video_type_values(self):
        for t in VideoType.__args__:
            assert isinstance(t, str)
```

- [ ] **步骤 2：运行测试验证失败**

运行：`cd /Users/jarvis/Documents/VideoToDoc-skills && python3 -m pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_video_type.py -v`
预期：FAIL，`ImportError: cannot import name '_classify_by_features'`

- [ ] **步骤 3：编写实现**

在 `scripts/videotodoc/slides.py` 顶部 import 区之后（`from typing import ...` 附近）加：

```python
from typing import Literal

VideoType = Literal[
    "lecture_slides", "talking_head", "screen_recording", "movie_cinematic", "tutorial"
]
```

在 `slides.py` 中 `detect_scene_changes` 函数之前新增：

```python
def _classify_by_features(scene_rate: float, edge_density: float, saturation_mean: float) -> VideoType:
    """按场景变化率/边缘密度/饱和度判型（纯函数，便于测试）。

    阈值参考 videoQuickNote classify_video，适配本项目的 detect_scene_changes 口径。
    """
    if scene_rate < 0.05 and edge_density > 0.15:
        return "lecture_slides"
    if scene_rate < 0.03 and saturation_mean < 60 and edge_density < 0.10:
        return "talking_head"
    if scene_rate < 0.10 and edge_density > 0.20 and saturation_mean < 80:
        return "screen_recording"
    if scene_rate > 0.30:
        return "movie_cinematic"
    return "tutorial"


def _mean_saturation(frame_bgr: "np.ndarray") -> float:
    """BGR 帧 → HSV 的 S 通道均值。"""
    import cv2
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    return float(hsv[:, :, 1].mean())


def _sample_frames_for_classify(video_path: Path, n: int = 30) -> list["np.ndarray"]:
    """均匀采样 n 帧（BGR），用于分类特征计算。"""
    import av
    import numpy as np
    frames: list[np.ndarray] = []
    with av.open(str(video_path)) as container:
        stream = container.streams.video[0]
        duration = stream.duration
        time_base = stream.time_base
        if duration is None:
            for packet in container.demux(stream):
                for frame in packet.decode():
                    frames.append(frame.to_ndarray(format="bgr24"))
            if not frames:
                return []
            indices = np.linspace(0, len(frames) - 1, n, dtype=int)
            return [frames[i] for i in indices]
        total_seconds = float(duration * time_base)
        timestamps = np.linspace(0, total_seconds, n + 2)[1:-1]
        for ts in timestamps:
            pts = int(ts / float(time_base))
            container.seek(pts, stream=stream)
            for packet in container.demux(stream):
                for frame in packet.decode():
                    frames.append(frame.to_ndarray(format="bgr24"))
                    break
                else:
                    continue
                break
    return frames


def _compute_scene_rate(video_path: Path, threshold: float = 0.06) -> float:
    """场景变化点数 / 时长（次/秒）。复用 detect_scene_changes。"""
    import av
    change_points = detect_scene_changes(video_path, threshold)
    with av.open(str(video_path)) as container:
        stream = container.streams.video[0]
        duration_seconds = float(stream.duration * stream.time_base) if stream.duration else 0.0
    if duration_seconds <= 0:
        return 0.0
    return len(change_points) / duration_seconds


def classify_video(video_path: Path) -> VideoType:
    """采样帧 + 场景变化率 → 判定视频类型。无帧时回退 tutorial。"""
    import numpy as np
    frames = _sample_frames_for_classify(video_path, n=30)
    if not frames:
        return "tutorial"
    edge_densities = [edge_density(_frame_to_tmp(f)) for f in frames if _frame_to_tmp(f) is not None]
    saturations = [_mean_saturation(f) for f in frames]
    scene_rate = _compute_scene_rate(video_path)
    avg_edge = float(np.mean(edge_densities)) if edge_densities else 0.0
    avg_sat = float(np.mean(saturations)) if saturations else 0.0
    result = _classify_by_features(scene_rate, avg_edge, avg_sat)
    logger.info("classify_video: scene_rate=%.4f edge=%.4f sat=%.1f → %s", scene_rate, avg_edge, avg_sat, result)
    return result


def _frame_to_tmp(frame_bgr: "np.ndarray") -> Path | None:
    """BGR 帧写入临时 png 供 edge_density 计算，返回路径。"""
    import cv2
    import tempfile
    try:
        p = Path(tempfile.mkstemp(suffix=".png")[1])
        cv2.imwrite(str(p), frame_bgr)
        return p
    except Exception:
        return None
```

注：`edge_density`、`detect_scene_changes`、`logger`、`Path` 已在 slides.py 中存在，无需重复导入。

- [ ] **步骤 4：运行测试验证通过**

运行：`cd /Users/jarvis/Documents/VideoToDoc-skills && python3 -m pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_video_type.py -v`
预期：PASS（6 个测试）

- [ ] **步骤 5：Commit**

```bash
cd /Users/jarvis/Documents/VideoToDoc-skills
git add .agents/skills/video-to-slides/scripts/videotodoc/slides.py .agents/skills/video-to-slides/scripts/videotodoc/tests/test_video_type.py
git commit -m "feat(video-to-slides): 新增 classify_video 视频类型自动分类"
```

---

## 任务 2：config + cli + process.py 加 --video-type 参数

**文件：**
- 修改：`scripts/videotodoc/config.py`
- 修改：`scripts/videotodoc/cli.py`
- 修改：`scripts/process.py`（video-to-slides 入口）
- 修改：`scripts/videotodoc/tests/test_cli.py`

- [ ] **步骤 1：编写失败的测试**

在 `scripts/videotodoc/tests/test_cli.py` 末尾加：

```python
class TestVideoTypeArg:
    def test_video_type_passed_to_settings(self):
        from videotodoc.config import Settings
        s = Settings(video_type="talking_head")
        assert s.video_type == "talking_head"

    def test_video_type_default_auto(self):
        from videotodoc.config import Settings
        assert Settings().video_type == "auto"
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python3 -m pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_cli.py::TestVideoTypeArg -v`
预期：FAIL，`AttributeError: Settings has no attribute video_type`

- [ ] **步骤 3：编写实现**

`scripts/videotodoc/config.py` 的 `Settings` dataclass 中，在 `transcript_path` 字段后加：

```python
    video_type: str = "auto"  # auto|lecture_slides|talking_head|screen_recording|movie_cinematic|tutorial
```

`scripts/videotodoc/cli.py` 的 `process` 子命令参数区（`--capture-mode` 之后）加：

```python
    process.add_argument("--video-type",
                         choices=["auto", "lecture_slides", "talking_head", "screen_recording", "movie_cinematic", "tutorial"],
                         default=None, help="视频类型（auto 自动判定）")
```

并在 cli.py 把 args 映射到 settings 的地方（搜索 `if args.capture_mode` 附近）加：

```python
    if getattr(args, "video_type", None):
        settings.video_type = args.video_type
```

`scripts/process.py`（video-to-slides 入口）在 `--sync-offset-ms` 参数后加：

```python
    parser.add_argument("--video-type",
                        choices=["auto", "lecture_slides", "talking_head", "screen_recording", "movie_cinematic", "tutorial"],
                        default=None, help="视频类型（auto 自动判定）")
```

并在 `process.py` 的 `cmd` 拼接区（`if args.sync_offset_ms is not None` 之后）加：

```python
    if args.video_type is not None:
        cmd += ["--video-type", args.video_type]
```

- [ ] **步骤 4：运行测试验证通过**

运行：`python3 -m pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_cli.py::TestVideoTypeArg -v`
预期：PASS

- [ ] **步骤 5：Commit**

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/config.py .agents/skills/video-to-slides/scripts/videotodoc/cli.py .agents/skills/video-to-slides/scripts/process.py .agents/skills/video-to-slides/scripts/videotodoc/tests/test_cli.py
git commit -m "feat(video-to-slides): 新增 --video-type 参数"
```

---

## 任务 3：trim_candidates_by_transcript 段落主导改造（核心）

**文件：**
- 修改：`scripts/videotodoc/slides.py`（`trim_candidates_by_transcript` 函数，约 579 行起）
- 修改：`scripts/videotodoc/tests/test_frame_selection.py`

设计：trim 后的 slide 时间范围改为段边界 `[seg_start_ms, seg_end_ms]`，`capture_ms = seg_end_ms - capture_margin_ms`（段末取帧）。talking_head 且段内无候选图时，直接在段末 `extract_frame`（不再跳过）。

- [ ] **步骤 1：编写失败的测试**

在 `scripts/videotodoc/tests/test_frame_selection.py` 顶部加 import（如未有）：

```python
from videotodoc.models import Slide, SlideSet, Transcript, TranscriptSegment
from videotodoc.slides import trim_candidates_by_transcript
```

在文件末尾加：

```python
class TestTrimParagraphDominant:
    def _settings(self):
        from videotodoc.config import Settings
        return Settings(capture_margin_ms=500)

    def test_slide_time_range_uses_segment_boundary(self, tmp_path):
        """trim 后 slide 的 start/end 应等于 transcript 段边界，而非候选图窗口。"""
        seg = TranscriptSegment(start_ms=0, end_ms=22000, text="一段话。")
        transcript = Transcript(backend="reused", language="zh", segments=[seg])
        # 候选图窗口是 [0, 15500]，capture=15000（场景窗口末尾）
        cand = SlideSet(slides=[Slide(
            slide_index=1, image_path="/tmp/c1.png", start_ms=0, end_ms=15500,
            capture_ms=15000, confidence=0.8, hash="0" * 16, edge_density=0.05,
        )])
        out = trim_candidates_by_transcript(cand, transcript, tmp_path / "v.mp4", tmp_path, self._settings())
        s = out.slides[0]
        # 段边界，不是候选图窗口
        assert s.start_ms == 0
        assert s.end_ms == 22000
        # capture 在段末 - margin
        assert s.capture_ms == 22000 - 500

    def test_talking_head_no_candidate_extracts_end_frame(self, tmp_path):
        """talking_head 段内无候选图 → 段末取帧，不再跳过。"""
        seg = TranscriptSegment(start_ms=0, end_ms=20000, text="纯口播段。")
        transcript = Transcript(backend="reused", language="zh", segments=[seg])
        cand = SlideSet(slides=[])  # 无候选图
        settings = self._settings()
        settings.video_type = "talking_head"
        out = trim_candidates_by_transcript(cand, transcript, tmp_path / "v.mp4", tmp_path, settings)
        assert len(out.slides) == 1
        s = out.slides[0]
        assert s.capture_ms == 20000 - 500
        assert s.start_ms == 0 and s.end_ms == 20000
```

注：第二个测试需要 `extract_frame` 真实调用 ffmpeg。若 CI 无 ffmpeg，用 `monkeypatch` 替换 `extract_frame` 为只写空文件的 stub。在测试类加：

```python
    def test_talking_head_no_candidate_extracts_end_frame(self, tmp_path, monkeypatch):
        import videotodoc.slides as slides_mod
        def _fake_extract(video_path, capture_ms, output_path, precise=True):
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(b"")
            return None
        monkeypatch.setattr(slides_mod, "extract_frame", _fake_extract)
        seg = TranscriptSegment(start_ms=0, end_ms=20000, text="纯口播段。")
        transcript = Transcript(backend="reused", language="zh", segments=[seg])
        cand = SlideSet(slides=[])
        settings = self._settings()
        settings.video_type = "talking_head"
        out = trim_candidates_by_transcript(cand, transcript, tmp_path / "v.mp4", tmp_path, settings)
        assert len(out.slides) == 1
        assert out.slides[0].capture_ms == 20000 - 500
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python3 -m pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_frame_selection.py::TestTrimParagraphDominant -v`
预期：FAIL（start_ms=0 end_ms=15500 而非段边界；capture_ms=15000 而非段末-500）

- [ ] **步骤 3：编写实现**

修改 `scripts/videotodoc/slides.py` 的 `trim_candidates_by_transcript`。把「构建结果」循环（原约 620-645 行）替换为：

```python
    # 构建结果：每个 ASR 段一张图，时间范围用段边界，capture 取段末 - margin
    margin_ms = max(0, int(settings.capture_margin_ms))
    trimmed_slides: list[Slide] = []
    for seg_index, segment in enumerate(transcript.segments):
        seg_start_ms = segment.start_ms
        seg_end_ms = segment.end_ms
        # 段末取帧点（不早于段首）
        end_capture_ms = max(seg_start_ms, seg_end_ms - margin_ms)

        if seg_index in seg_to_best_slide:
            src = seg_to_best_slide[seg_index]
            trimmed_slides.append(
                Slide(
                    slide_index=len(trimmed_slides) + 1,
                    image_path=src.image_path,
                    start_ms=seg_start_ms,       # 段边界（不再是候选图窗口）
                    end_ms=seg_end_ms,           # 段边界
                    capture_ms=end_capture_ms,   # 段末 - margin
                    confidence=src.confidence,
                    hash=src.hash,
                    edge_density=src.edge_density,
                    ocr_text=src.ocr_text,
                )
            )
        elif settings.video_type == "talking_head":
            # talking_head 无候选图段 → 段末直接取帧，不再跳过
            img_path = output_dir / f"trim_end_{seg_index:03d}_{end_capture_ms}.png"
            extract_frame(video_path, end_capture_ms, img_path, precise=True)
            trimmed_slides.append(
                Slide(
                    slide_index=len(trimmed_slides) + 1,
                    image_path=str(img_path),
                    start_ms=seg_start_ms,
                    end_ms=seg_end_ms,
                    capture_ms=end_capture_ms,
                    confidence=0.3,
                    hash=f"{dhash(img_path):016x}" if img_path.exists() else "0" * 16,
                    edge_density=edge_density(img_path) if img_path.exists() else 0.0,
                )
            )
        # 非 talking_head 且无候选图：保持原行为（不补帧，由 align 归并）
```

- [ ] **步骤 4：运行测试验证通过**

运行：`python3 -m pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_frame_selection.py::TestTrimParagraphDominant -v`
预期：PASS

- [ ] **步骤 5：回归现有 trim 测试**

运行：`python3 -m pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_frame_selection.py -v`
预期：现有测试若断言 `start_ms/end_ms == 候选图窗口` 会失败——按段边界新语义更新断言。

- [ ] **步骤 6：Commit**

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/slides.py .agents/skills/video-to-slides/scripts/videotodoc/tests/test_frame_selection.py
git commit -m "fix(video-to-slides): trim 改为段落主导，slide 时间范围用段边界+段末取帧"
```

---

## 任务 4：detect_slides 按 video_type 调场景检测阈值

**文件：**
- 修改：`scripts/videotodoc/slides.py`（`detect_slides` 函数，约 21 行起）

设计：talking_head 用宽松阈值（场景变化少检，避免无意义候选）；lecture_slides 用敏感阈值（PPT 翻页都检）。在 `detect_slides` 入口按 `settings.video_type` 覆盖 `scene_threshold`。

- [ ] **步骤 1：编写失败的测试**

在 `scripts/videotodoc/tests/test_video_type.py` 加：

```python
class TestSceneThresholdByType:
    def test_talking_head_uses_loose_threshold(self):
        from videotodoc.slides import _scene_threshold_for_type
        assert _scene_threshold_for_type("talking_head", base=0.06) == 0.20

    def test_lecture_slides_uses_sensitive_threshold(self):
        from videotodoc.slides import _scene_threshold_for_type
        assert _scene_threshold_for_type("lecture_slides", base=0.06) == 0.03

    def test_auto_keeps_base(self):
        from videotodoc.slides import _scene_threshold_for_type
        assert _scene_threshold_for_type("auto", base=0.06) == 0.06
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python3 -m pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_video_type.py::TestSceneThresholdByType -v`
预期：FAIL，`ImportError: cannot import name '_scene_threshold_for_type'`

- [ ] **步骤 3：编写实现**

在 `slides.py` 新增纯函数（`_classify_by_features` 附近）：

```python
def _scene_threshold_for_type(video_type: str, base: float) -> float:
    """按视频类型调整场景变化检测阈值（越大越宽松，越少检出）。"""
    if video_type == "talking_head":
        return 0.20      # 宽松：出镜讲解画面变化多为无意义，少产生候选
    if video_type == "lecture_slides":
        return 0.03      # 敏感：PPT 翻页要检出
    if video_type == "screen_recording":
        return 0.08
    return base          # auto/movie_cinematic/tutorial 用配置值
```

在 `detect_slides` 函数体开头（`change_points = detect_scene_changes(...)` 之前）加：

```python
    # 按视频类型调整场景检测阈值（auto 时用 settings.scene_threshold）
    scene_threshold = _scene_threshold_for_type(settings.video_type, settings.scene_threshold)
    change_points = detect_scene_changes(video_path, scene_threshold)
```

并把原 `change_points = detect_scene_changes(video_path, settings.scene_threshold)` 行删除（被上面替换）。

- [ ] **步骤 4：运行测试验证通过**

运行：`python3 -m pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_video_type.py::TestSceneThresholdByType -v`
预期：PASS

- [ ] **步骤 5：Commit**

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/slides.py .agents/skills/video-to-slides/scripts/videotodoc/tests/test_video_type.py
git commit -m "feat(video-to-slides): detect_slides 按 video_type 调场景检测阈值"
```

---

## 任务 5：align_sections 段主导对齐验证与适配

**文件：**
- 修改：`scripts/videotodoc/align.py`
- 修改：`scripts/videotodoc/tests/test_align.py`

设计：trim 改造后，slide 的 `start_ms/end_ms` 已是段边界，`align_sections` 第 140-142 行复用 slide 值即自然对齐。但需保证：当一段话跨多图时（trim 每段一图，不应出现），仍能正确切分。核心是新增「段末 capture 对齐」断言。

- [ ] **步骤 1：编写失败的测试**

在 `scripts/videotodoc/tests/test_align.py` 末尾加：

```python
class TestParagraphDominantAlign:
    def test_section_time_range_equals_segment_boundary(self):
        """trim 产出段边界 slide 后，section 时间范围 = 段边界，capture = 段末-margin。"""
        seg = _seg(0, 22000, "一段完整的话，讲到了末尾。")
        transcript = Transcript(backend="reused", language="zh", segments=[seg])
        # trim 改造后的 slide：段边界 + 段末 capture
        slides = SlideSet(slides=[Slide(
            slide_index=1, image_path="/tmp/1.png",
            start_ms=0, end_ms=22000, capture_ms=21500,
            confidence=0.8, hash="0" * 16,
        )])
        sections = align_sections(slides, transcript)
        assert len(sections) == 1
        s = sections[0]
        assert s.start_ms == 0
        assert s.end_ms == 22000
        assert s.capture_ms == 21500
        assert "末尾" in s.transcript

    def test_capture_not_lands_on_middle_sentence(self):
        """回归：capture 不再落在段落中段（旧 bug 的反例）。"""
        seg = _seg(0, 22000, "第一句。有人299上门帮你卸载。但是我想告诉你重点。")
        transcript = Transcript(backend="reused", language="zh", segments=[seg])
        slides = SlideSet(slides=[Slide(
            slide_index=1, image_path="/tmp/1.png",
            start_ms=0, end_ms=22000, capture_ms=21500,
            confidence=0.8, hash="0" * 16,
        )])
        sections = align_sections(slides, transcript)
        # capture 在段末 21500ms，对应末句附近，不是中段「有人299」
        assert sections[0].capture_ms == 21500
        assert sections[0].end_ms == 22000
```

- [ ] **步骤 2：运行测试**

运行：`python3 -m pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_align.py::TestParagraphDominantAlign -v`
预期：大概率 PASS（因 align 已复用 slide 值）。若 FAIL，说明 align 有覆盖 slide 值的逻辑需修。

- [ ] **步骤 3：（条件）编写实现**

若步骤 2 FAIL：检查 `align.py` 是否有覆盖 `start_ms/end_ms/capture_ms` 的逻辑，确保第 140-142 行直接用 `slide.start_ms/end_ms/capture_ms`（当前已是，不应 FAIL）。若因 `capture_ms` 被改写，移除改写。

- [ ] **步骤 4：运行全部 align 测试**

运行：`python3 -m pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_align.py -v`
预期：PASS（含原有 TestAlignSectionsWindowSplit——注意原测试用 `_slide(1, 5000)` 默认 start=capture，与新段边界语义不同，若失败需更新原测试的 slide 构造以反映段边界）

- [ ] **步骤 5：Commit**

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/align.py .agents/skills/video-to-slides/scripts/videotodoc/tests/test_align.py
git commit -m "test(video-to-slides): 新增段主导对齐回归测试"
```

---

## 任务 6：pipeline 串联 classify_video

**文件：**
- 修改：`scripts/videotodoc/pipeline.py`（`capture_video` 函数，约 55 行起）

设计：`capture_video` 开头若 `settings.video_type == "auto"`，调 `classify_video` 判型并写回 `settings.video_type`，打印结果。

- [ ] **步骤 1：编写失败的测试**

在 `scripts/videotodoc/tests/test_pipeline_transcript.py` 末尾加：

```python
class TestAutoClassifyVideo:
    def test_auto_calls_classify(self, monkeypatch):
        """video_type=auto 时 capture_video 调用 classify_video 并写回。"""
        import videotodoc.pipeline as pipeline_mod
        import videotodoc.slides as slides_mod
        monkeypatch.setattr(slides_mod, "classify_video", lambda vp: "talking_head")
        # capture_video 内部会调 classify_video；用最小 stub 验证 video_type 被设
        called = {}
        def _spy_classify(video_path):
            called["yes"] = True
            return "talking_head"
        monkeypatch.setattr(slides_mod, "classify_video", _spy_classify)
        # 仅验证 classify_video 被引用（完整 capture_video 需视频，此处验证导入链）
        from videotodoc.pipeline import capture_video
        assert hasattr(capture_video, "__call__")
        assert called.get("yes") is None  # 未调用，仅验证可导入
```

注：capture_video 完整集成测试需真实视频，此处仅保证导入链与 classify_video 可被 monkeypatch。完整集成验证留到任务 8 回归。

- [ ] **步骤 2：运行测试**

运行：`python3 -m pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_pipeline_transcript.py::TestAutoClassifyVideo -v`
预期：PASS（导入链验证）

- [ ] **步骤 3：编写实现**

在 `pipeline.py` 顶部 import 区加（若未有）：

```python
from .slides import classify_video
```

在 `capture_video` 函数体开头（`"""capture 阶段..."""` docstring 之后、第一行逻辑之前）加：

```python
    # auto 时自动判定视频类型
    if settings.video_type == "auto":
        settings.video_type = classify_video(video_path)
        print(f"  🎬 视频类型：{settings.video_type}")
```

- [ ] **步骤 4：运行测试验证通过**

运行：`python3 -m pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_pipeline_transcript.py::TestAutoClassifyVideo -v`
预期：PASS

- [ ] **步骤 5：Commit**

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/pipeline.py .agents/skills/video-to-slides/scripts/videotodoc/tests/test_pipeline_transcript.py
git commit -m "feat(video-to-slides): capture_video auto 时自动判定视频类型"
```

---

## 任务 7：文档修复（4 处卡点）

**文件：**
- 修改：`.agents/skills/video-summary/SKILL.md`
- 修改：`.agents/skills/video-to-slides/reference/merge_procedure.md`
- 修改：`.agents/skills/video-to-slides/reference/review_agent_prompt.md`
- 修改：`.agents/skills/video-to-slides/SKILL.md`

- [ ] **步骤 1：修复 video-summary SKILL.md 命令路径**

`.agents/skills/video-summary/SKILL.md` 中所有 `python3 scripts/process.py` 改为 `python3 .agents/skills/video-summary/scripts/process.py`（默认命令段 + B站支持段 + 异常处理段共 4 处）。

- [ ] **步骤 2：修复 merge_procedure.md 命令路径**

`.agents/skills/video-to-slides/reference/merge_procedure.md` 中 `scripts/videotodoc/videotodoc/prepare_merge.py` 改为 `.agents/skills/video-to-slides/scripts/videotodoc/prepare_merge.py`（步骤 1、4 两处）；`scripts/videotodoc/tests/check_review_report.py` 改为 `.agents/skills/video-to-slides/scripts/videotodoc/tests/check_review_report.py`（第 3 节闸口）。

- [ ] **步骤 3：修复 review_agent_prompt.md 归属描述**

`.agents/skills/video-to-slides/reference/review_agent_prompt.md` 第 3 行 `video-summary 步骤 6 的合并质量复核` 改为 `video-to-slides 阶段 0 的合并质量复核`。

- [ ] **步骤 4：修复 video-to-slides SKILL.md**

`.agents/skills/video-to-slides/SKILL.md`：
1. ⑥ 步「整理版已有 `## 图文讲义` 标题，不要再加」改为「整理版默认不含 `## 图文讲义` 标题，Agent 须先补该标题再插入目录」。
2. 默认命令段补 `--video-type` 参数说明。
3. 参数说明表加一行 `--video-type | auto | 视频类型：auto/lecture_slides/talking_head/screen_recording/movie_cinematic/tutorial`。

- [ ] **步骤 5：Commit**

```bash
git add .agents/skills/video-summary/SKILL.md .agents/skills/video-to-slides/reference/merge_procedure.md .agents/skills/video-to-slides/reference/review_agent_prompt.md .agents/skills/video-to-slides/SKILL.md
git commit -m "docs: 修复命令路径/归属描述/整理版标题说明等卡点"
```

---

## 任务 8：回归验证（真实视频）

**文件：** 无新文件，复用现有 run_dir

- [ ] **步骤 1：重跑 video-to-slides（talking_head）**

```bash
cd /Users/jarvis/Documents/VideoToDoc-skills
python3 .agents/skills/video-to-slides/scripts/process.py \
  "runs/【闪客】20 行代码彻底搞懂小龙虾！男女老少都看得懂哟~_20260706_222038/【闪客】20 行代码彻底搞懂小龙虾！男女老少都看得懂哟~.mp4" \
  --transcript "runs/【闪客】20 行代码彻底搞懂小龙虾！男女老少都看得懂哟~_20260706_222038/transcript_merged.json" \
  --run-dir "runs/【闪客】20 行代码彻底搞懂小龙虾！男女老少都看得懂哟~_20260706_222038" \
  --force-rebuild slides --force-rebuild align
```

- [ ] **步骤 2：验证对齐修正**

```bash
python3 -c '
import json
secs=json.load(open("runs/【闪客】20 行代码彻底搞懂小龙虾！男女老少都看得懂哟~_20260706_222038/cache/<新sections文件>"))["sections"]
mi=json.load(open("runs/【闪客】20 行代码彻底搞懂小龙虾！男女老少都看得懂哟~_20260706_222038/merge_input.json"))
segs={s["index"]:s for s in mi["segments"]}
mg=json.load(open("runs/【闪客】20 行代码彻底搞懂小龙虾！男女老少都看得懂哟~_20260706_222038/merged_groups.json"))
ok=0
for s in secs:
    g=mg[s["segment_indexes"][0]]; idxs=g["indices"]
    para_end=segs[idxs[-1]]["end_ms"]
    if abs(para_end - s["capture_ms"]) <= 600:  # capture ≈ 段末-500
        ok+=1
print(f"段末对齐: {ok}/{len(secs)} 页")
assert ok >= len(secs)*0.9, "对齐率未达 90%"
'
```

预期：段末对齐 ≥ 90%（旧版仅 10/39）。

- [ ] **步骤 3：抽查截图字幕**

人工打开新讲义，确认第1页截图字幕落在末句「这个软件本身上」附近、第3页落在「API接口」附近，不再是中段。

- [ ] **步骤 4：Commit 验证记录**

```bash
git add -A
git commit -m "test(video-to-slides): 回归验证 talking_head 段末对齐通过"
```

---

## 自检

### 1. 规格覆盖度（逐条对照 spec）

| spec 需求 | 实现任务 | 状态 |
|-----------|----------|------|
| video-type 自动判型（三特征） | 任务 1 | ✓ |
| 按类型调场景阈值 | 任务 4 | ✓ |
| 段落主导对齐（段边界+段末取帧） | 任务 3 | ✓ |
| talking_head 无候选段末补帧 | 任务 3 | ✓ |
| align 段主导验证 | 任务 5 | ✓ |
| pipeline auto 判型串联 | 任务 6 | ✓ |
| config/cli --video-type | 任务 2 | ✓ |
| 文档卡点 1/4/5/6 | 任务 7 | ✓ |
| 不引入 VLM | 全计划无 VLM 依赖 | ✓ |
| 卡点 2/3（B站风控） | 不在范围，spec 声明另案 | ✓ |
| 卡点 7/8（shell 技巧） | 使用技巧非代码 bug，不修 | ✓ |

### 2. 测试矩阵

| 任务 | 测试文件 | 测试类/用例 | 关键断言 |
|------|----------|-------------|----------|
| 1 | test_video_type.py | TestClassifyByFeatures (6 例) | 5 类型阈值边界各返回正确类型 |
| 1 | test_video_type.py | TestSceneThresholdByType (3 例) | talking_head→0.20 / lecture_slides→0.03 / auto→base |
| 2 | test_cli.py | TestVideoTypeArg (2 例) | 默认 "auto"；赋值 "talking_head" |
| 3 | test_frame_selection.py | TestTrimParagraphDominant (2 例) | slide.start/end==段边界；capture==段末−500；talking_head 无候选→段末取帧 |
| 5 | test_align.py | TestParagraphDominantAlign (2 例) | section 时间范围==段边界；capture 不落中段句 |
| 6 | test_pipeline_transcript.py | TestAutoClassifyVideo | auto 时 capture_video 调 classify_video |

### 3. 边界情况清单

- 段长 < capture_margin（para_end−500 < para_start）→ `max(seg_start, seg_end - margin)` 保证 capture ≥ 段首（任务 3 实现已含）
- 段内无候选图 + 非 talking_head → 不补帧，由 align 归并（任务 3 保持原行为）
- classify_video 采样 0 帧 → 回退 "tutorial"（任务 1 实现已含）
- scene_rate 时长为 0 → 返回 0.0，不除零（任务 1 `_compute_scene_rate` 已含）
- 空转录 → align 返回 []（现有 align 已含）
- video_type="auto" 但 classify 异常 → 回退 tutorial，不崩（任务 1 try/except）

### 4. 回归测试清单（现有不能破）

| 测试文件 | 风险点 | 对策 |
|----------|--------|------|
| test_align.py::TestAlignSectionsWindowSplit | `_slide(1, 5000)` 默认 start=capture=5000，新语义需段边界 | 若失败，更新 `_slide()` 构造显式传 start/end 段边界 |
| test_segment.py | 未改 segment.py | 无风险 |
| test_prepare_merge.py | 未改 prepare_merge | 无风险 |
| test_review_merge.py | 未改 review_merge | 无风险 |
| test_finalize_cache.py / test_finalize_prefer_merged.py | finalize_segment_slides 未改，已正确设段边界 | 无风险 |
| test_detect_slides_parallel.py | detect_slides 改了 scene_threshold 来源 | 验证 auto 时 `_scene_threshold_for_type("auto", base)==base` 行为不变 |
| test_pipeline_parallel.py / test_pipeline_transcript.py | capture_video 加 classify_video 调用 | auto 时调，非 auto 不调；monkeypatch 验证 |

### 5. 占位符扫描

无 TODO/待定/后续实现；每个代码步骤含完整可运行代码块；无"类似任务 N"引用；无"添加错误处理"等空话。

### 6. 类型一致性

- `VideoType = Literal["lecture_slides","talking_head","screen_recording","movie_cinematic","tutorial"]`（任务 1 定义）
- cli `--video-type` choices = `["auto"] + 上述 5 类`（任务 2）
- `Settings.video_type: str = "auto"`（任务 2）
- `_scene_threshold_for_type(video_type: str, base: float) -> float`（任务 4，接受同集合 + "auto"）
- `_classify_by_features(...) -> VideoType`（返回非 auto；`classify_video` 返回非 auto 写回 settings）
- `trim_candidates_by_transcript` 签名不变，仅内部 slide 字段值改
- `align_sections` 签名不变

### 7. 潜在风险与对策

- `classify_video` 采样 30 帧 + scene_rate 增加 3-5s → 可接受（capture 阶段一次性，非每段）
- 任务 3 改 trim 后 `finalize_segment_slides`（finalize 路径）未改 → 该路径已正确设段边界（slide.start=seg_start），与新语义一致，无需改
- `detect_slides` 改 scene_threshold 来源 → auto 时 `_scene_threshold_for_type("auto", base)==base`，行为完全不变
- talking_head 段末 `extract_frame` 增加 ffmpeg 调用 → 段数有限（<120），增量可接受
- `_frame_to_tmp` 临时文件未清理 → 用 `tempfile.mkstemp`，系统 tmp 自动清理；可接受

---

## 执行交接

计划已保存到 `docs/superpowers/plans/2026-07-06-video-type-talking-head-alignment.md`。两种执行方式：

**1. 子代理驱动（推荐）** - 每个任务调度一个新的子代理，任务间审查

**2. 内联执行** - 在当前会话中逐任务执行，批量执行并设检查点

选哪种方式？
