# 截图选帧优化 + 产物命名 + B站策略2修复 实施计划

> **For agentic workers:** REQUIRED SUB-_SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 video-to-slides 截图易截到过渡帧的问题；修复 `--run-dir` 复用时产物名 `video_` 前缀问题；修复 B站下载策略2重复调用未加载浏览器 cookies 的问题。

**Architecture:** 在 video-to-slides 内部把 `choose_capture_time` 从"段末后向稳定"改为"段内信息密度优先+有限后向漂移"；在 `process_video` 中 `--run-dir` 复用时从目录名推断标题；在 video-summary 的 B站下载路径中新增真正从浏览器读取 cookies 的函数并替换策略2调用。

**Tech Stack:** Python 3.12, ffmpeg, PIL, curl_cffi, browser_cookie3 (新增可选依赖), pytest

## Global Constraints

- 所有改动必须兼容现有 118 个 pytest 测试，新增测试后测试总数应增加。
- 不修改 SKILL.md 或用户文档（本次只做代码修复）。
- `browser_cookie3` 作为可选依赖：未安装时策略2 graceful 回退到 yt-dlp。
- 截图选帧搜索范围不得跨出当前 ASR segment，避免跑到下一个话题。
- 产物标题推断只在 `--run-dir` 复用路径时生效，不影响默认新建 run_dir 流程。
- 每次 task 结束后必须提交（frequent commits）。

---

## 文件结构

| 文件 | 责任 |
|------|------|
| `.agents/skills/video-to-slides/scripts/videotodoc/slides.py` | 截图选帧核心逻辑（`choose_capture_time`, `finalize_segment_slides`） |
| `.agents/skills/video-to-slides/scripts/videotodoc/config.py` | 新增选帧相关配置字段（漂移上限、信息密度阈值） |
| `.agents/skills/video-to-slides/scripts/videotodoc/pipeline.py` | `--run-dir` 复用时从 run_dir 名推断标题 |
| `.agents/skills/video-summary/scripts/process.py` | B站策略2真正加载浏览器 cookies |
| `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_frame_selection.py` | 新增选帧逻辑单元测试 |
| `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_run_dir_title.py` | 新增 run_dir 标题推断测试 |
| `.agents/skills/video-summary/scripts/tests/test_bilibili_browser_cookies.py` | 新增 B站浏览器 cookies 路径测试 |

---

## Task 1: 新增选帧配置字段

**Files:**
- Modify: `.agents/skills/video-to-slides/scripts/videotodoc/config.py:15-53`
- Test: `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_frame_selection.py`

**Interfaces:**
- Consumes: 无
- Produces: `Settings.frame_drift_back_seconds: float = 2.0`, `Settings.min_edge_density: float = 0.02`

- [ ] **Step 1: 写失败测试**

```python
# .agents/skills/video-to-slides/scripts/videotodoc/tests/test_frame_selection.py
from videotodoc.config import Settings


def test_settings_has_frame_drift_back_seconds():
    s = Settings()
    assert hasattr(s, "frame_drift_back_seconds")
    assert s.frame_drift_back_seconds == 2.0


def test_settings_has_min_edge_density():
    s = Settings()
    assert hasattr(s, "min_edge_density")
    assert s.min_edge_density == 0.02
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/jarvis/Documents/VideoToDoc-skills && .venv/bin/python -m pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_frame_selection.py -v`

Expected: `AttributeError: 'Settings' object has no attribute 'frame_drift_back_seconds'`

- [ ] **Step 3: 实现最小改动**

```python
# .agents/skills/video-to-slides/scripts/videotodoc/config.py
# 在 capture_margin_ms 后新增两行
    capture_margin_ms: int = 500
    frame_drift_back_seconds: float = 2.0
    min_edge_density: float = 0.02
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/jarvis/Documents/VideoToDoc-skills && .venv/bin/python -m pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_frame_selection.py -v`

Expected: 2 passed

- [ ] **Step 5: 提交**

```bash
cd /Users/jarvis/Documents/VideoToDoc-skills
git add .agents/skills/video-to-slides/scripts/videotodoc/config.py \
        .agents/skills/video-to-slides/scripts/videotodoc/tests/test_frame_selection.py
git commit -m "feat(config): add frame_drift_back_seconds and min_edge_density settings"
```

---

## Task 2: 默认帧信息密度检查 + 向前漂移秒级

**Files:**
- Modify: `.agents/skills/video-to-slides/scripts/videotodoc/slides.py:227-271`
- Test: `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_frame_selection.py`

**Interfaces:**
- Consumes: `Settings.frame_drift_back_seconds`, `Settings.min_edge_density`, `Settings.capture_margin_ms`
- Produces: `choose_capture_time` 返回 `(capture_ms: int, confidence: float)`，其中 capture_ms 在 `[seg_start, seg_end]` 内

- [ ] **Step 1: 写失败测试**

```python
# .agents/skills/video-to-slides/scripts/videotodoc/tests/test_frame_selection.py
from pathlib import Path
from unittest.mock import patch
from videotodoc.config import Settings
from videotodoc.slides import choose_capture_time


def test_choose_capture_time_drifts_forward_on_low_density(tmp_path):
    """默认帧信息密度低时，应向前（时间更早）漂移找到高密度帧。"""
    video_path = tmp_path / "v.mp4"
    video_path.write_bytes(b"fake")

    settings = Settings(
        capture_margin_ms=500,
        frame_drift_back_seconds=2.0,
        min_edge_density=0.02,
    )

    # segment [8000ms, 10000ms]，默认截图点是 9500ms
    # 9500ms 低密度（白），往前 9000ms 高密度（黑）
    def mock_extract_frame(vp, ms, out_path, precise=True):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        from PIL import Image
        color = {
            9000: (0, 0, 0),         # 高密度目标帧
            9500: (255, 255, 255),   # 默认低密度帧
        }.get(ms, (255, 255, 255))
        Image.new("RGB", (100, 100), color=color).save(out_path)

    with patch("videotodoc.slides.extract_frame", side_effect=mock_extract_frame):
        capture_ms, confidence = choose_capture_time(video_path, 8000, 10000, settings)

    # 应选中 9000ms，而非默认的 9500ms
    assert capture_ms == 9000
    assert confidence > 0.5


def test_choose_capture_time_keeps_default_when_dense(tmp_path):
    """默认帧信息密度足够时，不漂移。"""
    video_path = tmp_path / "v.mp4"
    video_path.write_bytes(b"fake")

    settings = Settings(
        capture_margin_ms=500,
        frame_drift_back_seconds=2.0,
        min_edge_density=0.02,
    )

    def mock_extract_frame(vp, ms, out_path, precise=True):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        from PIL import Image
        # 9500ms 默认帧就是高密度
        Image.new("RGB", (100, 100), color=(0, 0, 0)).save(out_path)

    with patch("videotodoc.slides.extract_frame", side_effect=mock_extract_frame):
        capture_ms, confidence = choose_capture_time(video_path, 8000, 10000, settings)

    assert capture_ms == 9500
    assert confidence > 0.5
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/jarvis/Documents/VideoToDoc-skills && .venv/bin/python -m pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_frame_selection.py -v`

Expected: FAIL（`choose_capture_time` 没有漂移逻辑）

- [ ] **Step 3: 实现轻量算法**

```python
# .agents/skills/video-to-slides/scripts/videotodoc/slides.py

def choose_capture_time(
    video_path: Path,
    start_ms: int,
    end_ms: int,
    settings: Settings,
    candidates_dir: Path | None = None,
) -> tuple[int, float]:
    """在 ASR 段末附近选一张信息量足够的截图。

    策略：
    1. 默认截图点为 end_ms - capture_margin_ms（保持原行为）。
    2. 计算默认帧的 edge_density；如果 >= min_edge_density，直接返回。
    3. 否则在 [default_ms - frame_drift_back_seconds, default_ms] 范围内
       按 250ms 步长向前（时间更早）搜索，选 edge_density 最高的帧。
    4. 搜索范围不跨出当前 segment [start_ms, end_ms]。
    5. 都没找到高密度帧时回退到默认点。

    注：这是轻量优化，只检查最终入选的 slide，不是全段扫描。
    """
    if end_ms <= start_ms:
        return start_ms, 0.1

    margin_ms = max(0, int(settings.capture_margin_ms))
    drift_ms = max(0, int(settings.frame_drift_back_seconds * 1000))
    step_ms = 250  # 250ms 步长，兼顾精度与速度

    default_ms = max(start_ms, end_ms - margin_ms)
    search_start = max(start_ms, default_ms - drift_ms)

    tmp_dir = tempfile.mkdtemp(prefix="videotodoc_frames_")
    try:
        def _get_frame(ms: int) -> tuple[Path, float]:
            """获取指定时间帧，优先复用候选图，否则临时精确提取。"""
            existing = None
            if candidates_dir and candidates_dir.exists():
                matches = list(candidates_dir.glob(f"candidate_*_{ms}.png"))
                if not matches:
                    matches = list(candidates_dir.glob(f"candidate_{ms}.png"))
                if matches:
                    existing = matches[0]

            if existing:
                frame_path = existing
            else:
                frame_path = Path(tmp_dir) / f"frame_{ms}.png"
                extract_frame(video_path, ms, frame_path, precise=True)

            return frame_path, edge_density(frame_path)

        # 默认帧优先
        default_path, default_density = _get_frame(default_ms)
        if default_density >= settings.min_edge_density:
            return default_ms, min(0.95, 0.5 + default_density * 10)

        # 默认帧信息密度低，向前漂移搜索
        best_ms = default_ms
        best_density = default_density
        for ms in range(default_ms - step_ms, search_start - 1, -step_ms):
            _, density = _get_frame(ms)
            if density > best_density:
                best_ms = ms
                best_density = density
                # 找到满足阈值的即可提前结束
                if density >= settings.min_edge_density:
                    break

        confidence = min(0.95, 0.5 + best_density * 10)
        return best_ms, confidence
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/jarvis/Documents/VideoToDoc-skills && .venv/bin/python -m pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_frame_selection.py -v`

Expected: 4 passed

- [ ] **Step 5: 运行全量测试确认无回归**

Run: `cd /Users/jarvis/Documents/VideoToDoc-skills && .venv/bin/python -m pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/ -q`

Expected: 119+ passed

- [ ] **Step 6: 提交**

```bash
cd /Users/jarvis/Documents/VideoToDoc-skills
git add .agents/skills/video-to-slides/scripts/videotodoc/slides.py \
        .agents/skills/video-to-slides/scripts/videotodoc/tests/test_frame_selection.py
git commit -m "feat(slides): 低密度截图向前漂移秒级搜索，避免过渡帧"
```

---

## Task 3: --run-dir 复用时从目录名推断标题

**Files:**
- Modify: `.agents/skills/video-to-slides/scripts/videotodoc/pipeline.py:340-384`
- Test: `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_run_dir_title.py`

**Interfaces:**
- Consumes: `process_video(video_path, runs_dir, settings, force_rebuild, run_dir)` 中的 `run_dir`
- Produces: 产物路径使用从 `run_dir` 名推断的 `slug`，函数签名不变

- [ ] **Step 1: 写失败测试**

```python
# .agents/skills/video-to-slides/scripts/videotodoc/tests/test_run_dir_title.py
from pathlib import Path
from unittest.mock import patch
from videotodoc.pipeline import process_video
from videotodoc.config import Settings


def test_process_video_uses_run_dir_name_for_slug(tmp_path):
    """--run-dir 复用 video-summary 目录时，产物名应从 run_dir 名推断，而非 video.mp4。"""
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"fake")
    run_dir = tmp_path / "我的测试视频_20260628_120000"
    run_dir.mkdir()

    settings = Settings()

    def noop(*args, **kwargs):
        pass

    def fake_extract(*args, **kwargs):
        return args[1]

    def fake_transcribe(*args, **kwargs):
        from videotodoc.models import Transcript
        return Transcript(segments=[])

    def fake_detect(*args, **kwargs):
        from videotodoc.models import SlideSet
        return SlideSet(slides=[])

    with patch("videotodoc.pipeline.extract_audio", side_effect=fake_extract), \
         patch("videotodoc.pipeline.transcribe_audio", side_effect=fake_transcribe), \
         patch("videotodoc.pipeline.detect_slides", side_effect=fake_detect), \
         patch("videotodoc.pipeline.estimate_sync_offset_ms", return_value=0), \
         patch("videotodoc.pipeline.align_sections", return_value=[]), \
         patch("videotodoc.pipeline.generate_mindmap", side_effect=noop), \
         patch("videotodoc.pipeline.render_mindmap_and_refresh_docs", side_effect=noop), \
         patch("videotodoc.pipeline.render_original_markdown", side_effect=noop), \
         patch("videotodoc.pipeline.render_compact_markdown", side_effect=noop), \
         patch("videotodoc.pipeline.ensure_semantic_markdown", side_effect=noop), \
         patch("videotodoc.pipeline.markdown_to_docx", return_value=None), \
         patch("videotodoc.pipeline.write_quality_report", side_effect=noop):
        result = process_video(video_path, tmp_path, settings, run_dir=run_dir)

    assert "我的测试视频" in result.markdown_path.name
    assert "video_讲义" not in result.markdown_path.name
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/jarvis/Documents/VideoToDoc-skills && .venv/bin/python -m pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_run_dir_title.py -v`

Expected: FAIL（断言失败，产物名含 `video_讲义`）

- [ ] **Step 3: 实现最小改动**

```python
# .agents/skills/video-to-slides/scripts/videotodoc/pipeline.py
# 在 process_video 开头，slug/ts 计算之前插入
import re


def _title_from_run_dir(run_dir: Path) -> str | None:
    """从复用的 run_dir 名推断视频标题，去掉时间戳后缀。"""
    stem = run_dir.name
    m = re.search(r"(.+)_\d{8}_\d{6}$", stem)
    if m:
        return m.group(1)
    return stem


def process_video(...):
    ...
    if run_dir is not None:
        run_dir = run_dir.resolve()
        title = _title_from_run_dir(run_dir)
    else:
        title = None

    slug = slugify(title or video_path.stem)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    ...
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/jarvis/Documents/VideoToDoc-skills && .venv/bin/python -m pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_run_dir_title.py -v`

Expected: 1 passed

- [ ] **Step 5: 运行全量测试确认无回归**

Run: `cd /Users/jarvis/Documents/VideoToDoc-skills && .venv/bin/python -m pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/ -q`

Expected: 119+ passed

- [ ] **Step 6: 提交**

```bash
cd /Users/jarvis/Documents/VideoToDoc-skills
git add .agents/skills/video-to-slides/scripts/videotodoc/pipeline.py \
        .agents/skills/video-to-slides/scripts/videotodoc/tests/test_run_dir_title.py
git commit -m "fix(pipeline): --run-dir 复用时从目录名推断产物标题"
```

---

## Task 4: B站策略2真正加载浏览器 cookies

**Files:**
- Modify: `.agents/skills/video-summary/scripts/process.py:405-443`, `.agents/skills/video-summary/scripts/process.py:595-612`
- Test: `.agents/skills/video-summary/scripts/tests/test_bilibili_browser_cookies.py`

**Interfaces:**
- Consumes: `cookies_from_browser: str | None`（"chrome"/"firefox"/"safari"/"edge"）
- Produces: `_load_browser_cookies(browser: str) -> dict[str, str]`, `_bilibili_get_stream_urls_with_browser_cookies(bvid, cid, browser)`

- [ ] **Step 1: 写失败测试**

```python
# .agents/skills/video-summary/scripts/tests/test_bilibili_browser_cookies.py
from unittest.mock import MagicMock, patch
from pathlib import Path


def test_load_browser_cookies_returns_dict(tmp_path):
    """_load_browser_cookies 应返回浏览器 cookie 字典。"""
    # 把 process.py 加到路径
    import sys
    sys.path.insert(0, "/Users/jarvis/Documents/VideoToDoc-skills/.agents/skills/video-summary/scripts")
    from process import _load_browser_cookies

    mock_cookie = MagicMock()
    mock_cookie.name = "SESSDATA"
    mock_cookie.value = "abc123"
    mock_cookie.domain = ".bilibili.com"

    with patch("browser_cookie3.chrome", return_value=[mock_cookie]):
        cookies = _load_browser_cookies("chrome")

    assert cookies.get("SESSDATA") == "abc123"


def test_bilibili_get_stream_urls_with_browser_cookies_uses_browser_cookie(monkeypatch):
    import sys
    sys.path.insert(0, "/Users/jarvis/Documents/VideoToDoc-skills/.agents/skills/video-summary/scripts")
    from process import _bilibili_get_stream_urls_with_browser_cookies

    captured_cookies = {}

    class FakeSession:
        def __init__(self, *args, **kwargs):
            self.cookies = MagicMock()
        def set(self, name, value, domain=None):
            captured_cookies[name] = value
        def get(self, url, timeout=20):
            resp = MagicMock()
            resp.json.return_value = {"code": -1}
            return resp

    monkeypatch.setattr("curl_cffi.requests.Session", FakeSession)
    monkeypatch.setattr("process._load_browser_cookies", lambda b: {"SESSDATA": "abc123"})

    _bilibili_get_stream_urls_with_browser_cookies("BV1xx", "12345", "chrome")
    assert captured_cookies.get("SESSDATA") == "abc123"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/jarvis/Documents/VideoToDoc-skills && .venv/bin/python -m pytest .agents/skills/video-summary/scripts/tests/test_bilibili_browser_cookies.py -v`

Expected: `ImportError` 或 `AttributeError`（函数不存在）

- [ ] **Step 3: 实现浏览器 cookies 加载**

```python
# .agents/skills/video-summary/scripts/process.py
# 在 _bilibili_get_stream_urls_with_cookies 函数之后新增

def _load_browser_cookies(browser: str, domain: str = ".bilibili.com") -> dict[str, str]:
    """从浏览器读取指定 domain 的 cookies。

    browser 可选：chrome, firefox, safari, edge。
    未安装 browser_cookie3 时返回空字典。
    """
    try:
        import browser_cookie3
    except ImportError:
        print("  ⚠️  未安装 browser_cookie3，无法读取浏览器 cookies")
        return {}

    loaders = {
        "chrome": browser_cookie3.chrome,
        "firefox": browser_cookie3.firefox,
        "safari": browser_cookie3.safari,
        "edge": browser_cookie3.edge,
    }
    loader = loaders.get(browser.lower())
    if loader is None:
        print(f"  ⚠️  不支持的浏览器：{browser}，跳过浏览器 cookies")
        return {}

    try:
        cj = loader(domain_name=domain)
        return {c.name: c.value for c in cj}
    except Exception as e:
        print(f"  ⚠️  读取 {browser} cookies 失败：{e}")
        return {}


def _bilibili_get_stream_urls_with_browser_cookies(
    bvid: str, cid: str, browser: str
) -> tuple[str | None, str | None, bool]:
    """从浏览器读取登录态 cookies 调 B站 playurl。"""
    from curl_cffi import requests as cffi_requests

    cookies = _load_browser_cookies(browser)
    if not cookies:
        return None, None, False

    s = cffi_requests.Session(impersonate="chrome")
    for name, value in cookies.items():
        s.cookies.set(name, value, domain=".bilibili.com")

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

- [ ] **Step 4: 替换策略2调用**

```python
# .agents/skills/video-summary/scripts/process.py:605-608
# 原代码：
#     print(f"  💡  策略2：使用 {cookies_from_browser} 浏览器 cookies 重试...")
#     v_url2, a_url2, is_v2 = _bilibili_get_stream_urls_with_cookies(bvid, cid)
# 改为：
                    print(f"  💡  策略2：使用 {cookies_from_browser} 浏览器 cookies 重试...")
                    v_url2, a_url2, is_v2 = _bilibili_get_stream_urls_with_browser_cookies(bvid, cid, cookies_from_browser)
                    if not is_v2 and v_url2:
                        return _bilibili_download(url, run_dir, title, stream_urls=(v_url2, a_url2))
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd /Users/jarvis/Documents/VideoToDoc-skills && .venv/bin/python -m pytest .agents/skills/video-summary/scripts/tests/test_bilibili_browser_cookies.py -v`

Expected: 2 passed

- [ ] **Step 6: 提交**

```bash
cd /Users/jarvis/Documents/VideoToDoc-skills
git add .agents/skills/video-summary/scripts/process.py \
        .agents/skills/video-summary/scripts/tests/test_bilibili_browser_cookies.py
git commit -m "fix(bilibili): 策略2真正加载浏览器 cookies 绕过 v_voucher"
```

---

## Task 5: 全量回归测试 + 视频实测

**Files:**
- 无代码改动
- 使用已有测试和真实视频验证

**Interfaces:**
- 无

- [ ] **Step 1: 全量单元测试**

Run: `cd /Users/jarvis/Documents/VideoToDoc-skills && .venv/bin/python -m pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/ .agents/skills/video-summary/scripts/tests/ -q`

Expected: 121+ passed

- [ ] **Step 2: 用真实视频验证截图改善**

选择之前出问题的视频（如小红书 MiniMax M3），复跑 video-to-slides 的 fast 模式，重点检查：

```bash
cd /Users/jarvis/Documents/VideoToDoc-skills
RUN_DIR="test_output/旗舰模型三块拼图终于凑齐，实测MiniMax M3_20260628_195701"
.venv/bin/python .agents/skills/video-to-slides/scripts/process.py \
  "$RUN_DIR/video.mp4" \
  --run-dir "$RUN_DIR" \
  --transcript "$RUN_DIR/transcript_merged.json" \
  --capture-mode fast \
  --output-dir test_output
```

人工检查 `selected_slides_*/` 目录：
- 第 15 页不应是纯过渡页
- 信息密度低的页应有明显改善

- [ ] **Step 3: 验证产物命名**

检查 `$RUN_DIR/` 下新产物文件名是否以 `旗舰模型三块拼图终于凑齐，实测MiniMax M3_` 开头，而非 `video_`。

- [ ] **Step 4: 验证 B站策略2（如条件允许）**

找一个会触发 v_voucher 的 B站视频：

```bash
.venv/bin/python .agents/skills/video-summary/scripts/process.py \
  "https://www.bilibili.com/video/BVxxxxxx" \
  --cookies-from-browser chrome \
  --output-dir test_output
```

确认日志中出现"策略2：使用 chrome 浏览器 cookies 重试..."且不再重复调用原 `_bilibili_get_stream_urls_with_cookies`。

- [ ] **Step 5: 提交测试结果记录（可选）**

如测试结果良好，可更新 `docs/superpowers/Module-A-optimization-changelog-2026-06-27.md` 追加一行：

```markdown
- 2026-06-28: 修复过渡帧截图、video_ 前缀、B站策略2 cookies 问题
```

- [ ] **Step 6: 提交最终改动**

```bash
cd /Users/jarvis/Documents/VideoToDoc-skills
git add -A
git commit -m "test: 全量回归 + 视频实测验证过渡帧/命名/B站cookies修复"
```

---

## Self-Review

**1. Spec coverage:**
- 过渡帧问题 → Task 1 + Task 2
- video_ 前缀问题 → Task 3
- B站策略2问题 → Task 4
- 测试和 review → Task 5

**2. Placeholder scan:** 无 TBD/TODO，所有步骤含完整代码和命令。

**3. Type consistency:**
- `_load_browser_cookies` 返回 `dict[str, str]` 与调用处一致
- `_title_from_run_dir` 返回 `str | None` 与 `slugify` 输入一致
- `choose_capture_time` 签名不变，返回 `(int, float)` 不变

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-06-28-frame-selection-naming-bilibili-fixes.md`.**

Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
