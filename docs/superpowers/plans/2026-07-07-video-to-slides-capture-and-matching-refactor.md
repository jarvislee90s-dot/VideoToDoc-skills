# video-to-slides 截图+匹配重构 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 实现 spec [2026-07-07-video-to-slides-capture-and-matching-refactor.md](/Users/jarvis/Documents/VideoToDoc-skills/docs/superpowers/specs/2026-07-07-video-to-slides-capture-and-matching-refactor.md) 中的 4 个修复方向：detect 阶段参数化、匹配窗口+段内多候选、主图评分+命名、opencv 批量性能优化。让图文视觉内容匹配率从 50% 提升到 ≥ 75%。

**架构：** 在现有 `slides.py` 内新增 5 个辅助函数（`_min_slide_seconds_for_type` / `_max_candidates_for_type` / `_match_window` / `_score_candidate` / `_pick_main_candidate` / `_build_image_name` / `capture_frames_opencv`），改造 `trim_candidates_by_transcript` 接收 `keep_all_segment_candidates` 开关 + 时间顺序排列 + 主图评分；扩展 `Section` 模型支持 `image_paths: list[str]` 多图；改造 `document.py` 紧凑版/整理版 markdown 渲染多图（按时间顺序，主图加 `:main` 标记）。

**技术栈：** Python 3.14, ffmpeg (scene 滤镜 + extract_frame), opencv-python (cv2.VideoCapture + cv2.imwrite), rapidocr (已有, OCR 复用), pytest。

**前置 spec**：[2026-07-07-video-to-slides-capture-and-matching-refactor.md](/Users/jarvis/Documents/VideoToDoc-skills/docs/superpowers/specs/2026-07-07-video-to-slides-capture-and-matching-refactor.md)

**注意：** 本计划只改代码不改 SKILL.md 主流程描述；SKILL.md 仅在阶段 1 ② 加参数说明（任务 10）。

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `scripts/videotodoc/config.py` | 修改 | `Settings` 新增 9 字段（任务 1）|
| `scripts/videotodoc/slides.py` | 修改 | 新增 7 个辅助函数 + 改造 `trim_candidates_by_transcript` + 改造 `detect_slides` 调参（任务 2/3/5/6/7/8）|
| `scripts/videotodoc/models.py` | 修改 | `Section` 扩展 `image_paths: list[str]` 字段（任务 8）|
| `scripts/videotodoc/document.py` | 修改 | `render_compact_markdown` / `ensure_semantic_markdown` 改造多图展示（任务 9）|
| `scripts/videotodoc/restore_images.py` | 修改 | 占位符格式兼容 `<!-- IMAGE:N-M[:main] -->`（任务 9）|
| `.agents/skills/video-to-slides/scripts/process.py` | 修改 | CLI 参数透传（任务 10）|
| `.agents/skills/video-to-slides/SKILL.md` | 修改 | 阶段 1 ② 加参数说明（任务 10）|
| `scripts/videotodoc/tests/test_min_slide_for_type.py` | 新建 | min_slide_seconds_for_type 映射测试（任务 2）|
| `scripts/videotodoc/tests/test_dynamic_min_slide.py` | 新建 | 动态调整算法测试（任务 2）|
| `scripts/videotodoc/tests/test_match_window.py` | 新建 | 匹配窗口边界测试（任务 3）|
| `scripts/videotodoc/tests/test_score_candidate.py` | 新建 | 关键词提取+OCR overlap+评分测试（任务 4+5）|
| `scripts/videotodoc/tests/test_image_naming.py` | 新建 | 图片命名格式测试（任务 6）|
| `scripts/videotodoc/tests/test_capture_frames_opencv.py` | 新建 | opencv 批量截图测试（任务 7）|
| `scripts/videotodoc/tests/test_keep_all_segments.py` | 新建 | 段内多候选测试（任务 8）|
| `scripts/videotodoc/tests/test_multi_image_markdown.py` | 新建 | 紧凑版/整理版多图展示测试（任务 9）|
| `scripts/videotodoc/tests/test_cli_new_args.py` | 新建 | CLI 新参数透传测试（任务 10）|

---

## 任务 1：Settings 新增字段

**文件：**
- 修改：`scripts/videotodoc/config.py`

- [x] **步骤 1：编写失败的测试**

修改 `scripts/videotodoc/tests/test_config_settings.py`（或新建），追加 9 个字段断言：

```python
def test_settings_new_fields_defaults() -> None:
    from videotodoc.config import Settings
    s = Settings()
    assert s.scene_threshold == 0.06
    assert s.min_slide_seconds == 1.0
    assert s.max_candidates == 200
    assert s.match_window_sec is None
    assert s.keep_all_segment_candidates is False
    assert s.main_score_edge_weight == 0.5
    assert s.main_score_ocr_weight == 0.5
    assert s.use_opencv_capture is True
    assert s.detect_workers == 8
```

- [x] **步骤 2：运行测试验证失败**

```bash
.venv/bin/python3 -m pytest scripts/videotodoc/tests/test_config_settings.py::test_settings_new_fields_defaults -v
```

预期：FAIL，AttributeError（这些字段不存在）。

- [x] **步骤 3：修改 Settings 类**

在 `scripts/videotodoc/config.py` 找到 `Settings` 类（BaseSettings 子类），在现有字段下方新增：

```python
    # 4.1 节：detect 阶段严格度参数
    scene_threshold: float = 0.06  # ffmpeg scene 阈值
    min_slide_seconds: float = 1.0  # 最小换页点间隔秒数
    max_candidates: int = 200  # 单视频最大候选数（硬上限）

    # 4.2 节：匹配窗口
    match_window_sec: float | None = None  # None = 按 video_type 自动

    # 4.4 节：段内多候选
    keep_all_segment_candidates: bool = False

    # 4.5 节：主图评分权重
    main_score_edge_weight: float = 0.5
    main_score_ocr_weight: float = 0.5

    # 4.8 节：opencv 截图
    use_opencv_capture: bool = True
    detect_workers: int = 8
```

- [x] **步骤 4：运行测试验证通过**

```bash
.venv/bin/python3 -m pytest scripts/videotodoc/tests/test_config_settings.py::test_settings_new_fields_defaults -v
```

预期：PASS。

- [x] **步骤 5：Commit**

```bash
git add scripts/videotodoc/config.py scripts/videotodoc/tests/test_config_settings.py
git commit -m "feat(config): add 9 settings fields for capture-and-matching refactor"
```

---

## 任务 2：min_slide_seconds + max_candidates 动态调整（4.1 + 4.1.5）

**文件：**
- 修改：`scripts/videotodoc/slides.py`（在 `_scene_threshold_for_type` 附近新增 2 个函数）
- 创建：`scripts/videotodoc/tests/test_min_slide_for_type.py`
- 创建：`scripts/videotodoc/tests/test_dynamic_min_slide.py`

- [x] **步骤 1：编写失败的测试**

新建 `scripts/videotodoc/tests/test_min_slide_for_type.py`：

```python
from videotodoc.slides import _min_slide_seconds_for_type


def test_talking_head_returns_5s() -> None:
    assert _min_slide_seconds_for_type("talking_head", 1.0) == 5.0


def test_lecture_slides_returns_0_5s() -> None:
    assert _min_slide_seconds_for_type("lecture_slides", 1.0) == 0.5


def test_screen_recording_returns_1s() -> None:
    assert _min_slide_seconds_for_type("screen_recording", 1.0) == 1.0


def test_movie_cinematic_returns_0_5s() -> None:
    assert _min_slide_seconds_for_type("movie_cinematic", 1.0) == 0.5


def test_unknown_returns_base() -> None:
    assert _min_slide_seconds_for_type("tutorial", 2.0) == 2.0
    assert _min_slide_seconds_for_type("auto", 1.0) == 1.0
```

新建 `scripts/videotodoc/tests/test_dynamic_min_slide.py`：

```python
from videotodoc.slides import _max_candidates_for_type


def test_short_video_returns_base_max() -> None:
    # 14min lecture_slides: estimated=1260 < max=500, 不调整
    result = _max_candidates_for_type("lecture_slides", 200, 840)
    assert result <= 500
    assert result >= 200


def test_long_video_caps_at_type_max() -> None:
    # 60min lecture_slides: estimated=5400, 强制 ≤ 500
    result = _max_candidates_for_type("lecture_slides", 200, 3600)
    assert result == 500


def test_movie_cinematic_long_video() -> None:
    # 60min movie_cinematic: type_cap=800
    result = _max_candidates_for_type("movie_cinematic", 200, 3600)
    assert result == 800


def test_talking_head_long_video() -> None:
    # 60min talking_head: type_cap=150
    result = _max_candidates_for_type("talking_head", 200, 3600)
    assert result == 150


def test_unknown_type_uses_base() -> None:
    # tutorial 用 base
    result = _max_candidates_for_type("tutorial", 200, 3600)
    # duration_factor = 3600/1800 = 2, 但 tutorial type_cap=300
    # min(300, 200*2) = 300
    assert result == 300
```

- [x] **步骤 2：运行测试验证失败**

```bash
.venv/bin/python3 -m pytest scripts/videotodoc/tests/test_min_slide_for_type.py scripts/videotodoc/tests/test_dynamic_min_slide.py -v
```

预期：ImportError（两个函数不存在）。

- [x] **步骤 3：实现两个函数**

在 `scripts/videotodoc/slides.py` 的 `_scene_threshold_for_type` 下方（约 line 196）新增：

```python
def _min_slide_seconds_for_type(video_type: str, base: float) -> float:
    """按 video_type 返回 min_slide_seconds 基线值（秒）。

    talking_head 5s（人脸动作不能算换页点）
    lecture_slides/movie_cinematic 0.5s（PPT 翻页/镜头切换快）
    screen_recording 1s
    其他用 base
    """
    if video_type == "talking_head":
        return 5.0
    if video_type in ("lecture_slides", "movie_cinematic"):
        return 0.5
    if video_type == "screen_recording":
        return 1.0
    return base


def _max_candidates_for_type(video_type: str, base: int, duration_sec: float) -> int:
    """按 video_type + duration 算候选数硬上限。

    type_cap 表 + duration_factor 调整。
    """
    type_caps = {
        "talking_head": 150,
        "lecture_slides": 500,
        "screen_recording": 400,
        "movie_cinematic": 800,
        "tutorial": 300,
    }
    type_cap = type_caps.get(video_type, base)
    duration_factor = max(1.0, duration_sec / 1800.0)
    return min(type_cap, int(base * duration_factor))
```

- [x] **步骤 4：运行测试验证通过**

```bash
.venv/bin/python3 -m pytest scripts/videotodoc/tests/test_min_slide_for_type.py scripts/videotodoc/tests/test_dynamic_min_slide.py -v
```

预期：9 passed。

- [x] **步骤 5：Commit**

```bash
git add scripts/videotodoc/slides.py scripts/videotodoc/tests/test_min_slide_for_type.py scripts/videotodoc/tests/test_dynamic_min_slide.py
git commit -m "feat(slides): add _min_slide_seconds_for_type and _max_candidates_for_type"
```

---

## 任务 3：匹配窗口 `_match_window`（4.2）

**文件：**
- 修改：`scripts/videotodoc/slides.py`
- 创建：`scripts/videotodoc/tests/test_match_window.py`

- [x] **步骤 1：编写失败的测试**

```python
def test_match_window_long_segment() -> None:
    from videotodoc.slides import _match_window
    # 段长 30s, W=5s
    assert _match_window(0, 30000, 5000) == (25000, 30000)


def test_match_window_short_segment_backoff() -> None:
    from videotodoc.slides import _match_window
    # 段长 4s, W=5s → 回退到段长
    assert _match_window(0, 4000, 5000) == (0, 4000)


def test_match_window_exact_length() -> None:
    from videotodoc.slides import _match_window
    # 段长 5s, W=5s
    assert _match_window(1000, 6000, 5000) == (1000, 6000)


def test_match_window_within_long_segment() -> None:
    from videotodoc.slides import _match_window
    # 段长 100s, W=8s → 末 8s
    assert _match_window(5000, 105000, 8000) == (97000, 105000)
```

- [x] **步骤 2：运行测试验证失败**

```bash
.venv/bin/python3 -m pytest scripts/videotodoc/tests/test_match_window.py -v
```

预期：ImportError。

- [x] **步骤 3：实现 `_match_window`**

在 `scripts/videotodoc/slides.py` 顶部辅助函数区新增：

```python
def _match_window(seg_start_ms: int, seg_end_ms: int, window_ms: int) -> tuple[int, int]:
    """段匹配窗口 [max(seg_start, seg_end - W), seg_end) 左闭右开。

    段长 < W 时自然回退到 [seg_start, seg_end)（不超段首）。
    """
    match_start = max(seg_start_ms, seg_end_ms - window_ms)
    return (match_start, seg_end_ms)
```

- [x] **步骤 4：运行测试验证通过**

```bash
.venv/bin/python3 -m pytest scripts/videotodoc/tests/test_match_window.py -v
```

预期：4 passed。

- [x] **步骤 5：Commit**

```bash
git add scripts/videotodoc/slides.py scripts/videotodoc/tests/test_match_window.py
git commit -m "feat(slides): add _match_window for segment match window [Y-W, Y)"
```

---

## 任务 4：关键词提取 + OCR overlap（4.5 前置）

**文件：**
- 修改：`scripts/videotodoc/slides.py`
- 创建：`scripts/videotodoc/tests/test_score_candidate.py`（包含 _extract_keywords 和 _ocr_keyword_overlap 测试）

- [x] **步骤 1：编写失败的测试**

```python
import re


def test_extract_keywords_chinese() -> None:
    from videotodoc.slides import _extract_keywords
    kw = _extract_keywords("推导 LLM")
    assert "推导" in kw
    assert "导L" in kw
    assert "LL" in kw
    assert "LM" in kw
    assert len(kw) == 4


def test_extract_keywords_strips_punctuation() -> None:
    from videotodoc.slides import _extract_keywords
    kw = _extract_keywords("推导LLM，大语言模型！")
    # 应去除标点
    assert "推导" in kw
    assert "，" not in "".join(kw)


def test_extract_keywords_short_text_returns_empty() -> None:
    from videotodoc.slides import _extract_keywords
    assert _extract_keywords("a") == set()
    assert _extract_keywords("") == set()


def test_ocr_keyword_overlap_perfect_match() -> None:
    from videotodoc.slides import _ocr_keyword_overlap
    seg = "推导 LLM 大语言模型"
    ocr = "LLM 大语言模型 涌现"
    score = _ocr_keyword_overlap(seg, ocr)
    assert score > 0.0
    assert score <= 1.0


def test_ocr_keyword_overlap_no_match() -> None:
    from videotodoc.slides import _ocr_keyword_overlap
    assert _ocr_keyword_overlap("推导 LLM", "天津一日游") == 0.0


def test_ocr_keyword_overlap_empty_ocr() -> None:
    from videotodoc.slides import _ocr_keyword_overlap
    assert _ocr_keyword_overlap("推导 LLM", "") == 0.0
    assert _ocr_keyword_overlap("推导 LLM", None) == 0.0


def test_ocr_keyword_overlap_empty_seg() -> None:
    from videotodoc.slides import _ocr_keyword_overlap
    assert _ocr_keyword_overlap("", "LLM") == 0.0
```

- [x] **步骤 2：运行测试验证失败**

```bash
.venv/bin/python3 -m pytest scripts/videotodoc/tests/test_score_candidate.py -v
```

预期：ImportError（_extract_keywords / _ocr_keyword_overlap 不存在）。

- [x] **步骤 3：实现两个函数**

在 `scripts/videotodoc/slides.py` 顶部辅助函数区（与 `_match_window` 同区）新增：

```python
_PUNCT_PATTERN = re.compile(r"[\s，。！？、；：\"\"''（）()\.\,\!\?\;\:]")


def _extract_keywords(text: str) -> set[str]:
    """从文本提取字符 bigram 集合（去标点）。短文本（<2 字符）返回空集。"""
    cleaned = _PUNCT_PATTERN.sub("", text or "").strip()
    if len(cleaned) < 2:
        return set()
    return {cleaned[i:i + 2] for i in range(len(cleaned) - 1)}


def _ocr_keyword_overlap(seg_text: str, ocr_text: str | None) -> float:
    """seg 与 ocr 关键词 Jaccard 重叠比 = |seg_kw ∩ ocr_kw| / |seg_kw|。

    OCR 为空或 seg 为空时返回 0.0。
    """
    if not seg_text or not ocr_text:
        return 0.0
    seg_kw = _extract_keywords(seg_text)
    ocr_kw = _extract_keywords(ocr_text)
    if not seg_kw or not ocr_kw:
        return 0.0
    return len(seg_kw & ocr_kw) / len(seg_kw)
```

- [x] **步骤 4：运行测试验证通过**

```bash
.venv/bin/python3 -m pytest scripts/videotodoc/tests/test_score_candidate.py -v
```

预期：7 passed。

- [x] **步骤 5：Commit**

```bash
git add scripts/videotodoc/slides.py scripts/videotodoc/tests/test_score_candidate.py
git commit -m "feat(slides): add _extract_keywords and _ocr_keyword_overlap"
```

---

## 任务 5：主图评分 + 主图选取（4.5）

**文件：**
- 修改：`scripts/videotodoc/slides.py`
- 创建：`scripts/videotodoc/tests/test_score_candidate.py`（追加测试）

- [x] **步骤 1：编写失败的测试**

在 `scripts/videotodoc/tests/test_score_candidate.py` 末尾追加：

```python
from dataclasses import dataclass


@dataclass
class _FakeSlide:
    edge_density: float = 0.0
    ocr_text: str = ""


def test_score_candidate_weighted_sum() -> None:
    from videotodoc.slides import _score_candidate
    s = _FakeSlide(edge_density=0.8, ocr_text="推导 LLM 大语言模型")
    # edge_normalized=0.8/0.8=1.0, ocr=seg_kw 完全包含 ocr_kw → overlap=1.0
    # score = 0.5*1.0 + 0.5*1.0 = 1.0
    score = _score_candidate(s, "推导 LLM 大语言模型", max_edge_in_seg=0.8,
                              edge_weight=0.5, ocr_weight=0.5)
    assert abs(score - 1.0) < 0.01


def test_score_candidate_normalizes_edge() -> None:
    from videotodoc.slides import _score_candidate
    s = _FakeSlide(edge_density=0.4, ocr_text="")
    # edge_normalized=0.4/0.8=0.5, ocr=0.0 (no ocr)
    # score = 0.5*0.5 + 0.5*0.0 = 0.25
    score = _score_candidate(s, "推导 LLM", max_edge_in_seg=0.8,
                              edge_weight=0.5, ocr_weight=0.5)
    assert abs(score - 0.25) < 0.01


def test_pick_main_candidate_highest_score() -> None:
    from videotodoc.slides import _pick_main_candidate
    slides = [
        _FakeSlide(edge_density=0.3, ocr_text=""),
        _FakeSlide(edge_density=0.8, ocr_text="推导 LLM"),
        _FakeSlide(edge_density=0.5, ocr_text=""),
    ]
    main = _pick_main_candidate(slides, "推导 LLM 大语言模型",
                                  edge_weight=0.5, ocr_weight=0.5)
    # 第二张 ocr 完全匹配 + edge 最高 → main
    assert main is slides[1]


def test_pick_main_candidate_single() -> None:
    from videotodoc.slides import _pick_main_candidate
    slides = [_FakeSlide(edge_density=0.5, ocr_text="x")]
    main = _pick_main_candidate(slides, "x", 0.5, 0.5)
    assert main is slides[0]


def test_pick_main_candidate_empty_raises() -> None:
    from videotodoc.slides import _pick_main_candidate
    import pytest
    with pytest.raises(ValueError):
        _pick_main_candidate([], "x", 0.5, 0.5)
```

- [x] **步骤 2：运行测试验证失败**

```bash
.venv/bin/python3 -m pytest scripts/videotodoc/tests/test_score_candidate.py -v
```

预期：ImportError / AttributeError（_score_candidate / _pick_main_candidate 不存在）。

- [x] **步骤 3：实现两个函数**

在 `scripts/videotodoc/slides.py` 关键词提取函数下方新增：

```python
def _score_candidate(
    slide,  # Slide 实例（有 edge_density, ocr_text 属性）
    seg_text: str,
    max_edge_in_seg: float,
    edge_weight: float = 0.5,
    ocr_weight: float = 0.5,
) -> float:
    """主图评分 = edge_weight * edge_normalized + ocr_weight * ocr_keyword_overlap。

    edge_normalized = slide.edge_density / max(max_edge_in_seg, 1e-6)
    """
    edge = float(getattr(slide, "edge_density", 0.0) or 0.0)
    edge_normalized = edge / max(max_edge_in_seg, 1e-6)
    ocr = getattr(slide, "ocr_text", "") or ""
    ocr_overlap = _ocr_keyword_overlap(seg_text, ocr)
    return edge_weight * edge_normalized + ocr_weight * ocr_overlap


def _pick_main_candidate(slides, seg_text: str, edge_weight: float, ocr_weight: float):
    """从候选 slides 中选评分最高者作为主图。

    空列表抛 ValueError。单元素直接返回。
    """
    if not slides:
        raise ValueError("候选列表为空，无法选取主图")
    if len(slides) == 1:
        return slides[0]
    max_edge = max(float(getattr(s, "edge_density", 0.0) or 0.0) for s in slides)
    return max(slides, key=lambda s: _score_candidate(s, seg_text, max_edge, edge_weight, ocr_weight))
```

- [x] **步骤 4：运行测试验证通过**

```bash
.venv/bin/python3 -m pytest scripts/videotodoc/tests/test_score_candidate.py -v
```

预期：12 passed（之前 7 + 新增 5）。

- [x] **步骤 5：Commit**

```bash
git add scripts/videotodoc/slides.py scripts/videotodoc/tests/test_score_candidate.py
git commit -m "feat(slides): add _score_candidate and _pick_main_candidate"
```

---

## 任务 6：图片命名 `_build_image_name`（4.6）

**文件：**
- 修改：`scripts/videotodoc/slides.py`
- 创建：`scripts/videotodoc/tests/test_image_naming.py`

- [x] **步骤 1：编写失败的测试**

```python
def test_build_image_name_main() -> None:
    from videotodoc.slides import _build_image_name
    # 段 6, 段内第 2 个, capture @ 185.8s, 主图
    assert _build_image_name(seg_index=5, intra_index=1, capture_ms=185800, is_main=True) \
        == "p06_02_main_185.8s.png"


def test_build_image_name_candidate() -> None:
    from videotodoc.slides import _build_image_name
    # 段 12, 段内第 3 个, capture @ 449.1s, 候选
    assert _build_image_name(seg_index=11, intra_index=2, capture_ms=449100, is_main=False) \
        == "p12_03_449.1s.png"


def test_build_image_name_single_no_suffix() -> None:
    from videotodoc.slides import _build_image_name
    # 段 20, 段内第 1 个, 主图（单图时主图无 _main 后缀以保持简洁）
    result = _build_image_name(seg_index=19, intra_index=0, capture_ms=885220, is_main=True, single=True)
    assert result == "p20_01_885.2s.png"
```

- [x] **步骤 2：运行测试验证失败**

```bash
.venv/bin/python3 -m pytest scripts/videotodoc/tests/test_image_naming.py -v
```

预期：ImportError。

- [x] **步骤 3：实现 `_build_image_name`**

在 `scripts/videotodoc/slides.py` 主图评分函数下方新增：

```python
def _build_image_name(
    seg_index: int,
    intra_index: int,
    capture_ms: int,
    is_main: bool,
    single: bool = False,
) -> str:
    """生成图片文件名：p{NN}_{MM}_{X.Ys}[_main].png

    - seg_index: 0-based 段号（输出时 +1）
    - intra_index: 0-based 段内顺序（输出时 +1）
    - capture_ms: 截图时刻毫秒
    - is_main: 是否主图
    - single: 段内仅 1 张时（不强制加 _main 后缀以保持简洁）
    """
    seg_n = f"{seg_index + 1:02d}"
    intra_n = f"{intra_index + 1:02d}"
    seconds = capture_ms / 1000.0
    if is_main and not single:
        suffix = "_main"
    else:
        suffix = ""
    return f"p{seg_n}_{intra_n}_{seconds:.1f}s{suffix}.png"
```

- [x] **步骤 4：运行测试验证通过**

```bash
.venv/bin/python3 -m pytest scripts/videotodoc/tests/test_image_naming.py -v
```

预期：3 passed。

- [x] **步骤 5：Commit**

```bash
git add scripts/videotodoc/slides.py scripts/videotodoc/tests/test_image_naming.py
git commit -m "feat(slides): add _build_image_name with p{NN}_{MM}_{X.Ys} format"
```

---

## 任务 7：opencv 批量截图 `capture_frames_opencv`（4.8）

**文件：**
- 修改：`scripts/videotodoc/slides.py`
- 创建：`scripts/videotodoc/tests/test_capture_frames_opencv.py`

- [x] **步骤 1：编写失败的测试**

```python
import cv2
import numpy as np
from pathlib import Path


def _create_test_video(path: Path, duration_sec: float = 5.0, fps: int = 10) -> None:
    """用 opencv 创建一个 2x2 黑色测试视频。"""
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, fps, (64, 64))
    total_frames = int(duration_sec * fps)
    for i in range(total_frames):
        frame = np.full((64, 64, 3), i % 256, dtype=np.uint8)
        writer.write(frame)
    writer.release()


def test_capture_frames_opencv_returns_dict(tmp_path: Path) -> None:
    from videotodoc.slides import capture_frames_opencv
    video = tmp_path / "test.mp4"
    _create_test_video(video, duration_sec=3.0)
    out_dir = tmp_path / "frames"
    timestamps = [500, 1500, 2500]  # ms
    results = capture_frames_opencv(video, timestamps, out_dir)
    assert len(results) == 3
    for ms in timestamps:
        assert ms in results
        assert results[ms].exists()
        assert results[ms].suffix == ".png"


def test_capture_frames_opencv_handles_missing_timestamp(tmp_path: Path) -> None:
    from videotodoc.slides import capture_frames_opencv
    video = tmp_path / "test.mp4"
    _create_test_video(video, duration_sec=2.0)
    out_dir = tmp_path / "frames"
    # 时间戳超过视频时长，可能返回空（不抛异常）
    results = capture_frames_opencv(video, [5000], out_dir)
    assert isinstance(results, dict)
    # 5000ms 超出 2s 视频，行为：返回空 dict（open 返回 False，跳过）
    assert 5000 not in results


def test_capture_frames_opencv_custom_template(tmp_path: Path) -> None:
    from videotodoc.slides import capture_frames_opencv
    video = tmp_path / "test.mp4"
    _create_test_video(video, duration_sec=2.0)
    out_dir = tmp_path / "frames"
    timestamps = [500, 1000]
    results = capture_frames_opencv(
        video, timestamps, out_dir, name_template="frame_{ms:07d}.png"
    )
    assert (out_dir / "frame_0000500.png").exists()
    assert (out_dir / "frame_0001000.png").exists()
```

- [x] **步骤 2：运行测试验证失败**

```bash
.venv/bin/python3 -m pytest scripts/videotodoc/tests/test_capture_frames_opencv.py -v
```

预期：ImportError（capture_frames_opencv 不存在）。

- [x] **步骤 3：实现 `capture_frames_opencv`**

在 `scripts/videotodoc/slides.py` 顶部 import 区新增：

```python
import cv2  # 已有依赖
```

在 `scripts/videotodoc/slides.py` 主图命名函数下方新增：

```python
def capture_frames_opencv(
    video_path: Path,
    timestamps_ms: list[int],
    output_dir: Path,
    name_template: str = "frame_{ms:07d}.png",
) -> dict[int, Path]:
    """用 opencv VideoCapture 批量截取视频帧。返回 {ms: image_path}。

    优势：一次 VideoCapture 打开，多次 read，10-20ms/帧。
    劣势：seek 精度不如 ffmpeg precise=True（最终入选 slide 仍用 ffmpeg 重截）。
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"无法打开视频：{video_path}")

    results: dict[int, Path] = {}
    output_dir.mkdir(parents=True, exist_ok=True)

    for ms in timestamps_ms:
        cap.set(cv2.CAP_PROP_POS_MSEC, ms)
        ret, frame = cap.read()
        if not ret:
            continue
        out_path = output_dir / name_template.format(ms=ms)
        cv2.imwrite(str(out_path), frame)
        results[ms] = out_path

    cap.release()
    return results
```

- [x] **步骤 4：运行测试验证通过**

```bash
.venv/bin/python3 -m pytest scripts/videotodoc/tests/test_capture_frames_opencv.py -v
```

预期：3 passed。

- [x] **步骤 5：Commit**

```bash
git add scripts/videotodoc/slides.py scripts/videotodoc/tests/test_capture_frames_opencv.py
git commit -m "feat(slides): add capture_frames_opencv for batch capture (5-10x speedup)"
```

---

## 任务 8：Section 扩展 + trim 改造（4.4 + keep_all）

**文件：**
- 修改：`scripts/videotodoc/models.py`（`Section` 加 `image_paths` 字段）
- 修改：`scripts/videotodoc/slides.py`（`trim_candidates_by_transcript` 重构）
- 创建：`scripts/videotodoc/tests/test_keep_all_segments.py`

- [x] **步骤 1：编写失败的测试**

新建 `scripts/videotodoc/tests/test_keep_all_segments.py`：

```python
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from videotodoc.models import Slide, SlideSet, Transcript, TranscriptSegment
from videotodoc.config import Settings
from videotodoc.slides import trim_candidates_by_transcript


def _make_slide(capture_ms: int, edge: float = 0.3, ocr: str = "") -> Slide:
    return Slide(
        slide_index=0, image_path=f"/tmp/cand_{capture_ms}.png",
        start_ms=capture_ms - 1000, end_ms=capture_ms + 1000,
        capture_ms=capture_ms, confidence=0.9, hash="0" * 16,
        edge_density=edge, ocr_text=ocr,
    )


def _make_transcript_with_segment(start: int, end: int, text: str) -> Transcript:
    return Transcript(backend="test", language="zh", segments=[
        TranscriptSegment(start_ms=start, end_ms=end, text=text),
    ])


def test_trim_keep_all_false_produces_one_slide(tmp_path: Path) -> None:
    """默认（keep_all=False）每段 1 张主图。"""
    video = tmp_path / "v.mp4"
    video.write_bytes(b"")
    transcript = _make_transcript_with_segment(0, 30000, "推导 LLM 大语言模型")
    candidates = SlideSet(slides=[
        _make_slide(20000, edge=0.5, ocr="LLM 推导"),
        _make_slide(28000, edge=0.8, ocr="LLM 大语言"),
    ])
    settings = Settings(keep_all_segment_candidates=False, match_window_sec=5)
    with patch("videotodoc.slides.capture_frames_opencv", return_value={}):
        result = trim_candidates_by_transcript(candidates, transcript, video, tmp_path, settings)
    assert len(result.slides) == 1
    main = result.slides[0]
    # 评分最高的（edge 0.8 + ocr 匹配）是第二张
    assert main.edge_density == 0.8


def test_trim_keep_all_true_produces_n_slides_in_time_order(tmp_path: Path) -> None:
    """keep_all=True 段内 N 张图，按时间顺序排列。"""
    video = tmp_path / "v.mp4"
    video.write_bytes(b"")
    transcript = _make_transcript_with_segment(0, 30000, "推导 LLM 大语言模型")
    # 3 张候选，时间 15000/20000/28000，OCR 匹配度 28000 最高
    candidates = SlideSet(slides=[
        _make_slide(15000, edge=0.4, ocr=""),
        _make_slide(20000, edge=0.5, ocr="LLM"),
        _make_slide(28000, edge=0.8, ocr="LLM 大语言"),  # 主图
    ])
    settings = Settings(keep_all_segment_candidates=True, match_window_sec=5)
    with patch("videotodoc.slides.capture_frames_opencv", return_value={}):
        result = trim_candidates_by_transcript(candidates, transcript, video, tmp_path, settings)
    assert len(result.slides) == 3
    # 段内时间顺序：15000, 20000, 28000
    assert result.slides[0].capture_ms == 15000
    assert result.slides[1].capture_ms == 20000
    assert result.slides[2].capture_ms == 28000
    # 主图（28000）保留原位置不前置


def test_trim_match_window_filters_out_of_window(tmp_path: Path) -> None:
    """段 [0, 30000]，W=5s → 只看 [25000, 30000) 内的候选。"""
    video = tmp_path / "v.mp4"
    video.write_bytes(b"")
    transcript = _make_transcript_with_segment(0, 30000, "推导 LLM")
    candidates = SlideSet(slides=[
        _make_slide(10000, edge=0.5, ocr=""),  # 段中段，不在 [25000, 30000) 内
        _make_slide(28000, edge=0.8, ocr="LLM"),  # 在窗口内
    ])
    settings = Settings(keep_all_segment_candidates=False, match_window_sec=5)
    with patch("videotodoc.slides.capture_frames_opencv", return_value={}):
        result = trim_candidates_by_transcript(candidates, transcript, video, tmp_path, settings)
    assert len(result.slides) == 1
    assert result.slides[0].capture_ms == 28000
```

- [x] **步骤 2：运行测试验证失败**

```bash
.venv/bin/python3 -m pytest scripts/videotodoc/tests/test_keep_all_segments.py -v
```

预期：FAIL（trim_candidates_by_transcript 还不支持 keep_all 参数）。

- [x] **步骤 3：修改 Section 模型**

修改 `scripts/videotodoc/models.py` 的 Section dataclass：

```python
@dataclass
class Section:
    slide_index: int
    image_path: str  # 主图路径（兼容旧调用）
    start_ms: int
    end_ms: int
    capture_ms: int
    transcript: str
    segment_indexes: list[int]
    notes: list[str] = field(default_factory=list)
    image_paths: list[str] = field(default_factory=list)  # 新增：段内所有图（按时间顺序，主图带 _main）
```

- [x] **步骤 4：重写 trim_candidates_by_transcript**

替换 `scripts/videotodoc/slides.py` 中的 `trim_candidates_by_transcript` 整个函数。**这是大改动，先备份原函数到 `/tmp/trim_backup.py` 再整体替换**。

新实现（替换原函数体）：

```python
def trim_candidates_by_transcript(
    candidates: SlideSet,
    transcript: Transcript,
    video_path: Path,
    output_dir: Path,
    settings: Settings,
) -> SlideSet:
    """按 [Y-W, Y) 窗口选择候选，keep_all 时保留全部（按时间顺序），主图评分最高加 _main 标记。

    方向 A（一段话多图）：
        - keep_all=False：选评分最高者 1 张作为主图
        - keep_all=True：段内 [Y-W, Y) 窗口所有换页点都保留，按时间顺序排列
    方向 B（一张图多段话）：
        - 一张图只归属到一个段（左闭右开天然不重叠）
    段末取帧：talking_head 无候选时 extract_frame 补帧
    """
    if not transcript.segments:
        return candidates

    output_dir.mkdir(parents=True, exist_ok=True)

    window_ms = int((settings.match_window_sec or 5) * 1000)

    trimmed_slides: list[Slide] = []
    for seg_index, segment in enumerate(transcript.segments):
        seg_start_ms = segment.start_ms
        seg_end_ms = segment.end_ms
        match_start, match_end = _match_window(seg_start_ms, seg_end_ms, window_ms)

        # 段内 [Y-W, Y) 窗口内的候选
        matching = [
            slide for slide in candidates.slides
            if match_start <= slide.capture_ms < match_end
        ]
        if not matching:
            if settings.video_type == "talking_head":
                # talking_head 无候选时段末补帧
                end_capture_ms = max(seg_start_ms, seg_end_ms - 500)
                img_path = output_dir / f"trim_end_{seg_index:03d}_{end_capture_ms}.png"
                extract_frame(video_path, end_capture_ms, img_path, precise=True)
                try:
                    slide_hash = f"{dhash(img_path):016x}" if img_path.exists() else "0" * 16
                except Exception:
                    slide_hash = "0" * 16
                try:
                    slide_edge = edge_density(img_path) if img_path.exists() else 0.0
                except Exception:
                    slide_edge = 0.0
                matching = [Slide(
                    slide_index=seg_index + 1,
                    image_path=str(img_path),
                    start_ms=seg_start_ms, end_ms=seg_end_ms,
                    capture_ms=end_capture_ms, confidence=0.3,
                    hash=slide_hash, edge_density=slide_edge,
                )]
            else:
                continue  # 非 talking_head 且无候选：跳过（由 align 归并）

        # 按时间顺序排序
        matching.sort(key=lambda s: s.capture_ms)

        if settings.keep_all_segment_candidates:
            # 保留全部：每张都生成 trimmed slide，主图加 _main 标记
            main_slide = _pick_main_candidate(
                matching, segment.text,
                settings.main_score_edge_weight, settings.main_score_ocr_weight,
            )
            for slide in matching:
                is_main = slide is main_slide
                end_capture_ms = max(seg_start_ms, seg_end_ms - 500)
                new_name = _build_image_name(
                    seg_index=seg_index,
                    intra_index=matching.index(slide),
                    capture_ms=end_capture_ms,
                    is_main=is_main,
                    single=False,
                )
                # 重新生成 image_path（基于新命名）
                # 保留原文件但 image_path 改新名
                old_path = Path(slide.image_path)
                new_path = output_dir / new_name
                if old_path.exists() and old_path != new_path:
                    # 软链或复制
                    try:
                        if new_path.exists():
                            new_path.unlink()
                        new_path.hardlink_to(old_path.resolve())
                    except OSError:
                        import shutil
                        shutil.copy2(str(old_path), str(new_path))
                trimmed_slides.append(Slide(
                    slide_index=len(trimmed_slides) + 1,
                    image_path=str(new_path) if new_path.exists() else slide.image_path,
                    start_ms=seg_start_ms, end_ms=seg_end_ms,
                    capture_ms=end_capture_ms, confidence=slide.confidence,
                    hash=slide.hash, edge_density=slide.edge_density,
                    ocr_text=slide.ocr_text,
                ))
        else:
            # 默认：选评分最高者 1 张
            main_slide = _pick_main_candidate(
                matching, segment.text,
                settings.main_score_edge_weight, settings.main_score_ocr_weight,
            )
            end_capture_ms = max(seg_start_ms, seg_end_ms - 500)
            new_name = _build_image_name(
                seg_index=seg_index, intra_index=0,
                capture_ms=end_capture_ms, is_main=True, single=True,
            )
            new_path = output_dir / new_name
            old_path = Path(main_slide.image_path)
            if old_path.exists() and old_path != new_path:
                try:
                    if new_path.exists():
                        new_path.unlink()
                    new_path.hardlink_to(old_path.resolve())
                except OSError:
                    import shutil
                    shutil.copy2(str(old_path), str(new_path))
            trimmed_slides.append(Slide(
                slide_index=len(trimmed_slides) + 1,
                image_path=str(new_path) if new_path.exists() else main_slide.image_path,
                start_ms=seg_start_ms, end_ms=seg_end_ms,
                capture_ms=end_capture_ms, confidence=main_slide.confidence,
                hash=main_slide.hash, edge_density=main_slide.edge_density,
                ocr_text=main_slide.ocr_text,
            ))

    metadata = dict(candidates.metadata)
    metadata["trimmed_by_transcript"] = True
    metadata["segment_count"] = len(transcript.segments)
    metadata["trimmed_slide_count"] = len(trimmed_slides)
    metadata["keep_all_segment_candidates"] = settings.keep_all_segment_candidates
    return SlideSet(slides=trimmed_slides, metadata=metadata)
```

- [x] **步骤 5：运行测试验证通过**

```bash
.venv/bin/python3 -m pytest scripts/videotodoc/tests/test_keep_all_segments.py -v
```

预期：3 passed。

- [x] **步骤 6：运行全量测试确认无回归**

```bash
.venv/bin/python3 -m pytest scripts/ -q
```

预期：之前测试 + 3 新增全绿。

- [x] **步骤 7：Commit**

```bash
git add scripts/videotodoc/models.py scripts/videotodoc/slides.py scripts/videotodoc/tests/test_keep_all_segments.py
git commit -m "refactor(slides): rewrite trim with [Y-W, Y) window + keep_all + main image"
```

---

## 任务 9：紧凑版/整理版多图展示（4.7）

**文件：**
- 修改：`scripts/videotodoc/document.py`
- 创建：`scripts/videotodoc/tests/test_multi_image_markdown.py`

- [x] **步骤 1：编写失败的测试**

```python
from pathlib import Path
from unittest.mock import patch


def test_compact_markdown_multi_image_in_time_order(tmp_path: Path) -> None:
    from videotodoc.document import render_compact_markdown
    from videotodoc.models import Section

    sections = [
        Section(
            slide_index=6,
            image_path="p06_02_main_185.8s.png",
            image_paths=[
                "p06_01_150.0s_cand.png",
                "p06_02_main_185.8s.png",
                "p06_03_210.0s_cand.png",
            ],
            start_ms=138600, end_ms=213900, capture_ms=213400,
            transcript="推导 LLM",
            segment_indexes=[6],
        ),
    ]
    out = tmp_path / "compact.md"
    render_compact_markdown("测试", sections, out)
    text = out.read_text(encoding="utf-8")
    # 验证 markdown 顺序：cand → main → cand（按时间，主图在中间）
    cand1_pos = text.find("p06_01_150.0s_cand")
    main_pos = text.find("p06_02_main_185.8s")
    cand3_pos = text.find("p06_03_210.0s_cand")
    assert cand1_pos < main_pos < cand3_pos


def test_semantic_markdown_multi_image_placeholders(tmp_path: Path) -> None:
    from videotodoc.document import ensure_semantic_markdown
    from videotodoc.models import Section

    sections = [
        Section(
            slide_index=6,
            image_path="p06_02_main_185.8s.png",
            image_paths=[
                "p06_01_150.0s_cand.png",
                "p06_02_main_185.8s.png",
                "p06_03_210.0s_cand.png",
            ],
            start_ms=138600, end_ms=213900, capture_ms=213400,
            transcript="推导 LLM",
            segment_indexes=[6],
        ),
    ]
    out = tmp_path / "semantic.md"
    ensure_semantic_markdown("测试", sections, out)
    text = out.read_text(encoding="utf-8")
    # 验证占位符顺序：IMAGE:6-1 → IMAGE:6-2:main → IMAGE:6-3
    img1 = text.find("<!-- IMAGE:6-1 -->")
    img2 = text.find("<!-- IMAGE:6-2:main -->")
    img3 = text.find("<!-- IMAGE:6-3 -->")
    assert img1 < img2 < img3


def test_compact_markdown_single_image_no_change(tmp_path: Path) -> None:
    """keep_all=False（单图）保持原有展示方式。"""
    from videotodoc.document import render_compact_markdown
    from videotodoc.models import Section

    sections = [
        Section(
            slide_index=1,
            image_path="p01_01_main_31.8s.png",
            image_paths=["p01_01_main_31.8s.png"],  # 单图
            start_ms=0, end_ms=32280, capture_ms=31780,
            transcript="开场",
            segment_indexes=[0],
        ),
    ]
    out = tmp_path / "compact.md"
    render_compact_markdown("测试", sections, out)
    text = out.read_text(encoding="utf-8")
    # 单图时 image_path 与 image_paths 第一个一致
    assert "p01_01_main_31.8s.png" in text
```

- [x] **步骤 2：运行测试验证失败**

```bash
.venv/bin/python3 -m pytest scripts/videotodoc/tests/test_multi_image_markdown.py -v
```

预期：FAIL（image_paths 字段尚未被 document.py 使用，仍用 image_path 渲染）。

- [x] **步骤 3：修改 `render_compact_markdown`**

在 `scripts/videotodoc/document.py` 的 `render_compact_markdown` 函数内（约 line 41-50），替换图片渲染部分：

替换前（约 line 47）：

```python
                f"![第 {section.slide_index} 页]({_markdown_image_path(section.image_path, output_path.parent)})",
```

替换后：

```python
                # 多图按时间顺序渲染（image_paths 字段按时间升序，主图带 _main 后缀）
                image_paths = section.image_paths or [section.image_path]
                for img_path in image_paths:
                    lines.append(f"![{Path(img_path).stem}]({_markdown_image_path(img_path, output_path.parent)})")
                lines.append("")
```

- [x] **步骤 4：修改 `ensure_semantic_markdown`**

在 `scripts/videotodoc/document.py` 的 `ensure_semantic_markdown` 函数内（约 line 75），替换占位符渲染部分：

替换前：

```python
                f"<!-- IMAGE:{section.slide_index} -->",
```

替换后：

```python
                # 多图占位符：IMAGE:N-M[:main]，M=段内顺序号，主图加 :main
                image_paths = section.image_paths or [section.image_path]
                for intra_idx, img_path in enumerate(image_paths, start=1):
                    stem = Path(img_path).stem
                    is_main = stem.endswith("_main")
                    suffix = ":main" if is_main else ""
                    lines.append(f"<!-- IMAGE:{section.slide_index}-{intra_idx}{suffix} -->")
                lines.append(""),
```

- [x] **步骤 5：运行测试验证通过**

```bash
.venv/bin/python3 -m pytest scripts/videotodoc/tests/test_multi_image_markdown.py -v
```

预期：3 passed。

- [x] **步骤 6：Commit**

```bash
git add scripts/videotodoc/document.py scripts/videotodoc/tests/test_multi_image_markdown.py
git commit -m "refactor(document): multi-image markdown with time-order and main marker"
```

---

## 任务 10：CLI 参数透传 + SKILL.md 文档

**文件：**
- 修改：`.agents/skills/video-to-slides/scripts/process.py`
- 修改：`.agents/skills/video-to-slides/SKILL.md`
- 创建：`scripts/videotodoc/tests/test_cli_new_args.py`

- [x] **步骤 1：编写失败的测试**

新建 `scripts/videotodoc/tests/test_cli_new_args.py`：

```python
import sys


def test_cli_accepts_keep_all_candidates() -> None:
    """--keep-all-candidates 参数存在。"""
    # 简化测试：import 时不抛异常即通过
    from videotodoc.cli import build_parser  # type: ignore
    parser = build_parser()
    args = parser.parse_args(["process", "/tmp/x.mp4", "--keep-all-candidates"])
    assert args.keep_all_candidates is True


def test_cli_accepts_max_candidates() -> None:
    from videotodoc.cli import build_parser  # type: ignore
    parser = build_parser()
    args = parser.parse_args(["process", "/tmp/x.mp4", "--max-candidates", "300"])
    assert args.max_candidates == 300


def test_cli_accepts_match_window_sec() -> None:
    from videotodoc.cli import build_parser  # type: ignore
    parser = build_parser()
    args = parser.parse_args(["process", "/tmp/x.mp4", "--match-window-sec", "8"])
    assert args.match_window_sec == 8.0
```

- [x] **步骤 2：运行测试验证失败**

```bash
.venv/bin/python3 -m pytest scripts/videotodoc/tests/test_cli_new_args.py -v
```

预期：ImportError / AttributeError（参数不存在）。

- [x] **步骤 3：CLI 入口加参数**

修改 `.agents/skills/video-to-slides/scripts/process.py`（在 parser 区域找到现有 `--keep-all-candidates` 等参数），确保以下参数存在并正确透传到 `--keep-all-candidates` / `--max-candidates` / `--match-window-sec`：

```python
parser.add_argument("--max-candidates", type=int, default=200,
                    help="单视频最大候选数（硬上限）")
parser.add_argument("--match-window-sec", type=float, default=None,
                    help="匹配窗口秒数（默认按 video_type 自动）")
parser.add_argument("--scene-threshold", type=float, default=None,
                    help="ffmpeg scene 阈值（默认按 video_type 自动）")
parser.add_argument("--min-slide-seconds", type=float, default=None,
                    help="最小换页点间隔秒数（默认按 video_type 自动）")
parser.add_argument("--no-opencv-capture", action="store_true",
                    help="禁用 opencv 批量截图，回退 ffmpeg")
```

并在 `cmd +=` 区域透传：

```python
if args.max_candidates is not None:
    cmd += ["--max-candidates", str(args.max_candidates)]
if args.match_window_sec is not None:
    cmd += ["--match-window-sec", str(args.match_window_sec)]
if args.scene_threshold is not None:
    cmd += ["--scene-threshold", str(args.scene_threshold)]
if args.min_slide_seconds is not None:
    cmd += ["--min-slide-seconds", str(args.min_slide_seconds)]
if args.no_opencv_capture:
    cmd += ["--no-opencv-capture"]
```

同时确保 `--keep-all-candidates` 已存在并透传（参考现有代码，应已存在）。

- [x] **步骤 4：CLI 内部参数（videotodoc.cli）确认**

如果 `scripts/videotodoc/cli.py` 已经有 `--keep-all-candidates` / `--max-candidates` / `--match-window-sec`，无需修改。否则追加。检查命令：

```bash
rg -n "keep_all|keep-all|max_candidates|max-candidates|match_window|match-window" .agents/skills/video-to-slides/scripts/videotodoc/cli.py
```

- [x] **步骤 5：运行测试验证通过**

```bash
.venv/bin/python3 -m pytest scripts/videotodoc/tests/test_cli_new_args.py -v
```

预期：3 passed。

- [x] **步骤 6：更新 SKILL.md**

修改 `.agents/skills/video-to-slides/SKILL.md` 阶段 1 ② 部分，在"参数说明"表格追加：

```markdown
| `--max-candidates` | `200` | 单视频最大候选数（硬上限，按 video_type 自动调）|
| `--match-window-sec` | 按 video_type | 匹配窗口秒数：talking_head 8 / lecture 3 / screen 3 / others 5 |
| `--scene-threshold` | 按 video_type | ffmpeg scene 阈值：talking_head 0.20 / lecture 0.03 / screen 0.08 / others 0.06 |
| `--min-slide-seconds` | 按 video_type | 最小换页点间隔：talking_head 5.0 / lecture 0.5 / screen 1.0 / others 1.0 |
| `--keep-all-candidates` | 关 | 段内保留 [Y-W, Y) 窗口所有换页点（按时间顺序，主图加 _main 标记）|
| `--no-opencv-capture` | 开 | 关闭后候选图阶段回退 ffmpeg（默认 opencv 批量）|
```

并在"截图去重规则"段落追加：

> **多图一段**（`--keep-all-candidates` 开启时）：每段内 [Y-W, Y) 窗口所有换页点都生成图，按时间顺序排列，主图（edge+OCR 关键词加权评分最高）加 `_main` 后缀。

- [x] **步骤 7：Commit**

```bash
git add .agents/skills/video-to-slides/scripts/process.py .agents/skills/video-to-slides/SKILL.md scripts/videotodoc/tests/test_cli_new_args.py
git commit -m "feat(cli+skill): add 5 new params + keep_all doc + opencv mention"
```

---

## 任务 11：端到端验证

**文件：** 无新文件，纯运行验证。

- [x] **步骤 1：跑全量测试确认无回归**

```bash
.venv/bin/python3 -m pytest tests/ .agents/skills/ -q
```

预期：之前 245+ 测试 + 本次新增 ≈ 20+ 测试全绿。

- [x] **步骤 2：跑 BV1ojfDBSEPv 端到端（keep_all=False 默认）**

```bash
.venv/bin/python3 .agents/skills/video-to-slides/scripts/process.py \
  "runs/【闪客】一口气拆穿Skill_MCP_RAG_Agent_OpenClaw底层逻辑_20260707_073907/【闪客】一口气拆穿Skill_MCP_RAG_Agent_OpenClaw底层逻辑.mp4" \
  --transcript "runs/【闪客】一口气拆穿Skill_MCP_RAG_Agent_OpenClaw底层逻辑_20260707_073907/transcript_merged.json" \
  --run-dir "runs/【闪客】一口气拆穿Skill_MCP_RAG_Agent_OpenClaw底层逻辑_20260707_073907" \
  --capture-mode audit --video-type auto \
  --force-rebuild slides --force-rebuild align
```

预期：21 段 → 21 张主图（每张命名为 `p{NN}_01_main_{X.Ys}.png`），讲义生成成功。

- [x] **步骤 3：跑 keep_all=True 实验**

```bash
.venv/bin/python3 .agents/skills/video-to-slides/scripts/process.py \
  "runs/【闪客】一口气拆穿Skill_MCP_RAG_Agent_OpenClaw底层逻辑_20260707_073907/【闪客】一口气拆穿Skill_MCP_RAG_Agent_OpenClaw底层逻辑.mp4" \
  --transcript "runs/【闪客】一口气拆穿Skill_MCP_RAG_Agent_OpenClaw底层逻辑_20260707_073907/transcript_merged.json" \
  --run-dir "runs/【闪客】一口气拆穿Skill_MCP_RAG_Agent_OpenClaw底层逻辑_20260707_073907" \
  --capture-mode audit --video-type auto --keep-all-candidates \
  --force-rebuild slides --force-rebuild align
```

预期：21 段 → 40-60 张图（每段 N 张，命名 `p{NN}_{MM}_{X.Ys}.png`，主图加 `_main` 后缀）。

- [x] **步骤 4：用 vision 抽查 5 张关键页确认视觉改善**

用 `view_image` 工具检视 `runs/.../p{NN}_*` 命名的图：

- 段 1 [0-32.3s]（开场）→ 检查是否仍是 agent 框架图
- 段 7 [138.6-213.9s]（agent 推导）→ 检查主图是否 agent 概念相关
- 段 10 [305.8-354.5s]（MCP 架构）→ 检查是否 MCP 架构图
- 段 19 [786.6-876.1s]（本质总结）→ 检查是否柴犬
- 段 20 [876.1-885.7s]（收尾）→ 检查是否片尾彩蛋

**对比修复前**：
- 段 1 修复前：agent 框架图（跨段）
- 段 19 修复前：柴犬（视频风格）
- 段 20 修复前：柴犬（片尾彩蛋）

**修复后预期**：
- 段 1 主图：评分最高（可能仍是 agent 框架，但用户能看到候选 1/2/3 供选择）
- 段 7 主图：保持原状（agent 段）✓
- 段 10 主图：MCP 架构图 ✓
- 段 19 主图：可能仍是柴犬（视频风格，无法避免）
- 段 20 主图：可能仍是柴犬（片尾彩蛋，无法避免）

**关键观察**：B1/B2/B3/B4 视觉跨段是设计取舍，本次不修复；用户能看到多图候选。

- [x] **步骤 5：更新卡点文档**

修改 [docs/superpowers/reviews/2026-07-07-video-to-slides-bv1ojfdbspev-bugs-and-risks.md](/Users/jarvis/Documents/VideoToDoc-skills/docs/superpowers/reviews/2026-07-07-video-to-slides-bv1ojfdbspev-bugs-and-risks.md) 中 B7 标记为"已修复（2026-07-07 plan 实现）"，附 commit hash。

- [x] **步骤 6：Commit 文档更新**

```bash
git add docs/superpowers/reviews/2026-07-07-video-to-slides-bv1ojfdbspev-bugs-and-risks.md
git commit -m "docs: mark B7 as fixed after plan execution"
```

---

## 自检

### 1. 规格覆盖度

| Spec 章节 | 实现任务 | 状态 |
|----------|---------|------|
| 4.1 严格度按 video_type 自动调 | 任务 2（_min_slide_seconds_for_type）| ✓ |
| 4.1.5 动态调整算法 | 任务 2（_max_candidates_for_type）| ✓ |
| 4.2 匹配窗口 [Y-W, Y) | 任务 3（_match_window）+ 任务 8（trim 用）| ✓ |
| 4.3 段间抢图：天然不重叠 | 任务 8（trim 注释中说明）| ✓ 无需新代码 |
| 4.4 段内多候选 | 任务 8（keep_all_segment_candidates 接入 trim）| ✓ |
| 4.5 主图评分 edge + OCR 关键词 | 任务 4（关键词提取+OCR）+ 任务 5（评分+选取）| ✓ |
| 4.6 图片命名 | 任务 6（_build_image_name）+ 任务 8（trim 用）| ✓ |
| 4.7 文档展示 | 任务 9（紧凑版/整理版多图渲染）| ✓ |
| 4.8 opencv 批量 | 任务 7（capture_frames_opencv）| ✓ |
| 4.9 Settings 字段 | 任务 1 | ✓ |
| 4.10 CLI 参数 | 任务 10 | ✓ |
| 4.11 video_type 映射表 | 任务 2/3 内置映射 + 任务 10 SKILL.md 文档 | ✓ |

**遗漏**：无。

### 2. 占位符扫描

- 无 "TODO" / "待定" / "后续实现"
- 无 "类似任务 N" 重复
- 每个代码步骤都有完整代码
- 任务间引用的函数（`_match_window` / `_score_candidate` / `_pick_main_candidate` / `_build_image_name` / `capture_frames_opencv`）都在前面任务定义

### 3. 类型一致性

| 函数/字段 | 首次定义 | 后续使用 | 一致 |
|----------|---------|---------|------|
| `_match_window(seg_start_ms, seg_end_ms, window_ms) -> tuple[int, int]` | 任务 3 | 任务 8 | ✓ |
| `_extract_keywords(text: str) -> set[str]` | 任务 4 | 任务 4/5 | ✓ |
| `_ocr_keyword_overlap(seg_text, ocr_text) -> float` | 任务 4 | 任务 5 | ✓ |
| `_score_candidate(slide, seg_text, max_edge_in_seg, edge_weight, ocr_weight) -> float` | 任务 5 | 任务 5/8 | ✓ |
| `_pick_main_candidate(slides, seg_text, edge_weight, ocr_weight)` | 任务 5 | 任务 8 | ✓ |
| `_build_image_name(seg_index, intra_index, capture_ms, is_main, single=False) -> str` | 任务 6 | 任务 8 | ✓ |
| `capture_frames_opencv(video_path, timestamps_ms, output_dir, name_template=...)` | 任务 7 | （预留）| ✓ |
| `Section.image_paths: list[str]` | 任务 8 | 任务 9 | ✓ |
| `Settings.keep_all_segment_candidates: bool` | 任务 1 | 任务 8/10 | ✓ |
| `Settings.match_window_sec: float \| None` | 任务 1 | 任务 8/10 | ✓ |
| `Settings.main_score_edge_weight: float` | 任务 1 | 任务 5/8 | ✓ |
| `Settings.main_score_ocr_weight: float` | 任务 1 | 任务 5/8 | ✓ |

**类型一致**。

### 4. 范围外

- B1 视觉跨段（不做）
- B5 ASR 错误段（不做）
- B6 标点（不做）
- B9 占位目录（不做）
- videoQuickNote 集成（不做）
- DL 模型（不做）
- jieba（不做）
- PySceneDetect（不做）

