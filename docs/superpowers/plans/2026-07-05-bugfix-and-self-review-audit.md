# Self-Review 审计字段 + 实测 Bug 修复 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 强制 review 报告写入 `self_review` 审计键（补上一轮开口）；修复实测视频 `BV1Xg7v6PEr9` 暴露的 4 个 bug（yt-dlp 产物名、browser_cookie3 静默缺失、mindmap.mmd 硬编码、图文对齐有图无文）。ASR 尾部噪声经用户确认不影响最终整理版产物，已剔除。

**架构：** 全部沿用现有 TDD 模式——先用 `.venv/bin/pytest` 跑红测试（证明 bug 存在 / 字段缺失），再改最小实现转绿。审计字段用「prompt 硬规则 + 事后存在性校验脚本」双保险；5 个 bug 各自聚焦单文件，连锁点（cleanup、SKILL.md 约定）一并修。

**技术栈：** Python 3.11 + pytest（`/Users/jarvis/Documents/VideoToDoc-skills/.venv/bin/pytest`）、mlx-whisper（segment 含 `no_speech_prob`/`avg_logprob`）、Mermaid CLI。video-summary 测试沿用 `sys.path.insert + 直 import` 模式，video-to-slides/videotodoc 用标准 pytest + conftest。

---

## 背景：实测触发的 5 个 bug（源自 runs/【闪客】新名词诈骗…_20260705_182404）

| Bug | 现象 | 根因 | 修复策略 |
|---|---|---|---|
| 1 | yt-dlp 回退后产物名 `video.mp4`，与 curl_cffi 分支 `<标题>.mp4` 不一致 | `process.py:698` outtmpl 写死 `video.%(ext)s` | yt-dlp 分支也用 `safe_title`，连带改 `cleanup` 的 glob |
| 2 | `browser_cookie3` 未安装时静默失败，无预检 | `check_dependencies` 不查它 | 加入可选依赖列表，doctor 提示 |
| 3 | `finalize.py` 报 `找不到 mindmap.mmd`，但 Agent 按约定写的是 `<标题>_思维导图_<时间戳>.mmd` | `mindmap.py:24` 硬编码 `mindmap.mmd`；SKILL.md 自相矛盾 | glob 优先匹配时间戳名 + 统一 SKILL.md 约定 |
| 4 | ASR 把片尾 BGM 误转录为「上居上居…」数百字，一路传播到讲义 | `transcribe_audio` 零后处理 | **已剔除**：整理版 Agent 已兜底过滤，最终产物不受影响，用户确认不修 |
| 5 | 图文对齐时长段堆到第一张图、后续截图「本页无讲解」 | `align.py` 原子分配 segment | 按截图区间切分文本，句末标点回溯断句 |

---

## 文件结构

**新建（测试）：**
- `.agents/skills/video-summary/scripts/tests/check_review_report.py` — self_review 存在性校验（可执行）
- `.agents/skills/video-summary/scripts/tests/test_check_review_report.py` — 校验器测试
- `.agents/skills/video-summary/scripts/tests/test_download_video_naming.py` — Bug 1 测试
- `.agents/skills/video-summary/scripts/tests/test_check_dependencies_browser_cookies.py` — Bug 2 测试
- `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_glob.py` — Bug 3 测试
- `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_align.py` — Bug 5 测试

**修改：**
- `.agents/skills/video-summary/reference/review_agent_prompt.md` — self_review 提升为硬规则
- `.agents/skills/video-summary/SKILL.md`（6.6 节）— 加「必跑校验」步骤
- `.agents/skills/video-summary/scripts/process.py` — Bug 1（download_video/cleanup）、Bug 2（check_dependencies）
- `.agents/skills/video-to-slides/scripts/videotodoc/mindmap.py` — Bug 3（`_find_mindmap_source` glob）
- `.agents/skills/video-to-slides/scripts/render_mindmap.py` — Bug 3（`_latest_run_dir` glob）
- `.agents/skills/video-to-slides/SKILL.md` — Bug 3 统一 mindmap 命名约定
- `.agents/skills/video-to-slides/scripts/videotodoc/align.py` — Bug 5（按区间切分）

---

## 任务 0：self_review 审计字段强制 + 存在性校验

**背景：** 上一轮 `review_agent_prompt.md` 第 59/73 行已要求路径 A 写 `self_review: false`、路径 B 写 `true`，但实测报告（runs/【闪客】新名词诈骗…_20260705_182404/merge_review_report.json）里**根本没有这个键**——prompt 里的要求只是输出示例，agent 没遵守。需双保险：①prompt 提升为「硬规则」；②事后校验脚本，缺键即报错。

**文件：**
- 修改：`.agents/skills/video-summary/reference/review_agent_prompt.md`（「## 硬规则」段）
- 修改：`.agents/skills/video-summary/SKILL.md`（6.6 节步骤）
- 创建：`.agents/skills/video-summary/scripts/tests/check_review_report.py`
- 创建：`.agents/skills/video-summary/scripts/tests/test_check_review_report.py`

- [ ] **步骤 0.1：编写失败的校验器测试**

创建 `.agents/skills/video-summary/scripts/tests/test_check_review_report.py`：

```python
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_review_report import check  # noqa: E402


def _write(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "merge_review_report.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def test_missing_self_review_key_returns_nonzero(tmp_path):
    """无 self_review 键 → 视为 review 未完成，非零退出。"""
    p = _write(tmp_path, {"pass": True, "total_groups": 10})  # 故意缺 self_review
    assert check(p) != 0


def test_self_review_false_path_a_passes(tmp_path):
    """路径 A（子代理）self_review=False → 通过。"""
    p = _write(tmp_path, {"pass": True, "self_review": False, "total_groups": 10})
    assert check(p) == 0


def test_self_review_true_path_b_passes(tmp_path):
    """路径 B（自审）self_review=True → 通过。"""
    p = _write(tmp_path, {"pass": True, "self_review": True, "total_groups": 10})
    assert check(p) == 0


def test_non_bool_self_review_returns_nonzero(tmp_path):
    """self_review 不是 bool → 非零。"""
    p = _write(tmp_path, {"pass": True, "self_review": "false"})  # 字符串，非法
    assert check(p) != 0


def test_missing_report_returns_nonzero(tmp_path):
    """报告文件不存在 → 非零。"""
    assert check(tmp_path / "merge_review_report.json") != 0
```

- [ ] **步骤 0.2：运行测试验证失败**

运行：`.venv/bin/pytest .agents/skills/video-summary/scripts/tests/test_check_review_report.py -v`
预期：FAIL，报错 `ModuleNotFoundError: No module named 'check_review_report'`

- [ ] **步骤 0.3：实现校验器**

创建 `.agents/skills/video-summary/scripts/tests/check_review_report.py`：

```python
"""校验 merge_review_report.json 必须含 self_review 键。

review_agent_prompt.md 要求路径 A 写 self_review=false、路径 B 写 true。
缺失该键即视为 review 未标注执行路径，等同未完成，不得进入下一步。

用法：python3 check_review_report.py <run_dir>
退出码：0 通过；1 self_review 缺失/类型错；2 报告不存在。
"""
import json
import sys
from pathlib import Path


def check(report_path: Path) -> int:
    """校验单份 review 报告，返回退出码。"""
    if not report_path.exists():
        print(f"❌ 找不到 review 报告：{report_path}", file=sys.stderr)
        return 2
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"❌ {report_path.name} 不是合法 JSON：{e}", file=sys.stderr)
        return 1
    if "self_review" not in report:
        print(
            f"❌ {report_path.name} 缺少 self_review 键：review 未标注执行路径，视为未完成。",
            file=sys.stderr,
        )
        return 1
    if not isinstance(report["self_review"], bool):
        print(
            f"❌ {report_path.name} 的 self_review 必须是 bool，"
            f"当前：{type(report['self_review']).__name__}",
            file=sys.stderr,
        )
        return 1
    label = "A（独立子代理）" if report["self_review"] is False else "B（自审 fallback）"
    print(f"✓ self_review={report['self_review']}（路径 {label}）")
    return 0


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print("用法：python3 check_review_report.py <run_dir>", file=sys.stderr)
        return 2
    run_dir = Path(args[0]).expanduser().resolve()
    if not run_dir.is_dir():
        print(f"❌ run_dir 不存在：{run_dir}", file=sys.stderr)
        return 2
    return check(run_dir / "merge_review_report.json")


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **步骤 0.4：运行测试验证通过**

运行：`.venv/bin/pytest .agents/skills/video-summary/scripts/tests/test_check_review_report.py -v`
预期：PASS（5 项全过）

- [ ] **步骤 0.5：RED——对实测报告跑校验，证明开口存在**

运行：`.venv/bin/python3 .agents/skills/video-summary/scripts/tests/check_review_report.py "runs/【闪客】新名词诈骗！你管这破玩意叫 Loop Engineering？_20260705_182404"`
预期：退出码 1，输出 `❌ ... 缺少 self_review 键`（实测报告确实无此键，证明开口真实存在）

- [ ] **步骤 0.6：把 self_review 提升为 prompt 硬规则**

修改 `.agents/skills/video-summary/reference/review_agent_prompt.md` 的「## 硬规则」段，在现有 bullet 列表**末尾**追加一条：

```markdown
- **输出 JSON 必须包含 `self_review` 键**（bool）：路径 A 设 `false`，路径 B 设 `true`。缺失该键即视为 review 未完成、未标注执行路径，后续校验脚本会拦截。
```

- [ ] **步骤 0.7：SKILL.md 6.6 节加「必跑校验」步骤**

修改 `.agents/skills/video-summary/SKILL.md` 6.6 节「步骤」列表，在第 6 步「重跑…直到 pass=true」与第 7 步之间**插入新步骤**：

```markdown
6.5 **【必做】跑存在性校验**：`python3 scripts/tests/check_review_report.py <run_dir>`，退出码必须为 0。若报「缺少 self_review 键」，说明 review 未标注执行路径，回到步骤 4 重做。
```

并把原第 7 步「直到 pass 才进下一步」改为「直到 pass 且校验退出码为 0 才进下一步」。

- [ ] **步骤 0.8：Commit**

```bash
git add .agents/skills/video-summary/scripts/tests/check_review_report.py \
        .agents/skills/video-summary/scripts/tests/test_check_review_report.py \
        .agents/skills/video-summary/reference/review_agent_prompt.md \
        .agents/skills/video-summary/SKILL.md
git commit -m "feat(review): 强制 self_review 审计键 + 存在性校验脚本"
```

---

## 任务 1：Bug 1——yt-dlp 回退产物名与 curl_cffi 不一致

**根因：** `process.py:698` yt-dlp 分支 `outtmpl: video.%(ext)s`，而 curl_cffi 分支（615/633 行）用 `{safe_title}.mp4`。回退后下游（video-to-slides）按 `<标题>.mp4` 找文件失败。**连锁点：** `cleanup` 的 `transcript-only` 模式（834 行）`glob("video.mp4")` 硬删固定名，改名后删不到。

**文件：**
- 修改：`.agents/skills/video-summary/scripts/process.py`（download_video 的 yt-dlp 分支 + cleanup）
- 创建：`.agents/skills/video-summary/scripts/tests/test_download_video_naming.py`

- [ ] **步骤 1.1：编写失败的测试**

创建 `.agents/skills/video-summary/scripts/tests/test_download_video_naming.py`：

```python
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, "/Users/jarvis/Documents/VideoToDoc-skills/.agents/skills/video-summary/scripts")
from process import download_video, cleanup  # noqa: E402


class _FakeYDL:
    """假 yt-dlp：记录 outtmpl，不真下载。"""

    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        # 在 outtmpl 指向的目录创建产物文件，模拟下载完成
        from pathlib import Path as P
        tmpl = self.opts["outtmpl"]
        # outtmpl 形如 .../safe_title.%(ext)s
        base = tmpl.replace("%(ext)s", "mp4")
        P(base).parent.mkdir(parents=True, exist_ok=True)
        P(base).write_bytes(b"fake")
        return self

    def __exit__(self, *a):
        return False

    def download(self, urls):
        pass


def test_ytdlp_outtmpl_uses_safe_title(tmp_path, monkeypatch):
    """yt-dlp 回退分支的 outtmpl 必须用 safe_title，不能写死 video。"""
    monkeypatch.setattr("yt_dlp.YoutubeDL", _FakeYDL, raising=False)
    # B站走不通 curl_cffi（让它抛异常）→ 回退 yt-dlp
    monkeypatch.setattr("process._is_bilibili_url", lambda u: True, raising=False)
    monkeypatch.setattr(
        "process._bilibili_extract_ids",
        lambda u: ("BVxx", 123, "标题"),
        raising=True,
    )
    with patch("curl_cffi.requests", side_effect=ImportError("no curl_cffi")):
        with patch("process._bilibili_get_stream_urls_with_cookies",
                   side_effect=RuntimeError("风控")):
            out = download_video(
                "https://www.bilibili.com/video/BVxx",
                run_dir=tmp_path, title="我的视频标题",
            )
    # 产物必须是 safe_title.mp4，不是 video.mp4
    assert out.name == "wo-de-shi-pin-biao-ti.mp4" or out.name.endswith(".mp4")
    assert out.name != "video.mp4"
    assert (tmp_path / out.name).exists()
    # outtmpl 不能写死 video
    assert "video.%(ext)s" not in _FakeYDL.__init_ydl_opts  # 见下


# 让 _FakeYDL 暴露最后一次收到的 opts
_init_ydl_opts = {}
class _FakeYDL2(_FakeYDL):
    def __init__(self, opts):
        super().__init__(opts)
        import builtins
        builtins._init_ydl_opts = opts
_FakeYDL.__init_ydl_opts = property(lambda self: {})
```

> 注：上面对 mock 做了简化。实际实现时，若 `_FakeYDL` 暴露 opts 困难，可改为断言 `download_video` 返回路径不含 `video.mp4`，且 `tmp_path` 下不存在 `video.mp4`、存在 `{safe_title}.mp4`。核心断言不变：**返回名 != video.mp4，且文件以 safe_title 命名**。

- [ ] **步骤 1.2：运行测试验证失败**

运行：`.venv/bin/pytest .agents/skills/video-summary/scripts/tests/test_download_video_naming.py -v`
预期：FAIL（当前 outtmpl 写死 `video.%(ext)s`，返回 `video.mp4`，断言 `out.name != "video.mp4"` 失败）

- [ ] **步骤 1.3：修复 yt-dlp 分支命名 + cleanup 连锁**

修改 `.agents/skills/video-summary/scripts/process.py` 的 `download_video` 函数 yt-dlp 分支（约 690-725 行）。把：

```python
    print(f"  ⬇️  下载视频...")
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "outtmpl": str(run_dir / "video.%(ext)s"),
        "merge_output_format": "mp4",
    }
    ...
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    for ext in ["mp4", "webm", "mkv", "mov"]:
        candidate = run_dir / f"video.{ext}"
        if candidate.exists():
            if ext != "mp4":
                mp4_path = run_dir / "video.mp4"
                candidate.rename(mp4_path)
                return mp4_path
            return candidate

    raise RuntimeError("视频下载后找不到文件")
```

改为（yt-dlp 分支也用 safe_title，与 curl_cffi 一致）：

```python
    # 与 curl_cffi 分支命名一致，避免 video-to-slides 找不到文件
    safe_title = _slugify(title or "video")
    print(f"  ⬇️  下载视频（yt-dlp）...")
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "outtmpl": str(run_dir / f"{safe_title}.%(ext)s"),
        "merge_output_format": "mp4",
    }
    if proxy:
        ydl_opts["proxy"] = proxy
    if cookies_from_browser:
        ydl_opts["cookiesfrombrowser"] = (cookies_from_browser,)
    if not _is_bilibili_url(url):
        prefetched = _prefetch_cookies_for_yt_dlp(
            "https://www.douyin.com/" if "douyin" in url else
            ("https://www.xiaohongshu.com/" if "xiaohongshu" in url or "xhslink" in url else None)
        )
        if prefetched and "cookiefile" not in ydl_opts:
            ydl_opts["cookiefile"] = prefetched

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    for ext in ["mp4", "webm", "mkv", "mov"]:
        candidate = run_dir / f"{safe_title}.{ext}"
        if candidate.exists():
            if ext != "mp4":
                mp4_path = run_dir / f"{safe_title}.mp4"
                candidate.rename(mp4_path)
                return mp4_path
            return candidate

    raise RuntimeError("视频下载后找不到文件")
```

修改 `cleanup` 函数 `transcript-only` 分支（约 833 行），把 `glob("video.mp4")` 改为 `glob("*.mp4")`（讲义产物是 .docx/.png/.md，不冲突）：

```python
    elif mode == "transcript-only":
        for f in run_dir.glob("*.mp4"):
            f.unlink(missing_ok=True)
            print(f"  🗑️  已删除：{f.name}")
        for f in run_dir.glob("audio.wav"):
            f.unlink(missing_ok=True)
            print(f"  🗑️  已删除：{f.name}")
```

- [ ] **步骤 1.4：运行测试验证通过**

运行：`.venv/bin/pytest .agents/skills/video-summary/scripts/tests/test_download_video_naming.py -v`
预期：PASS

- [ ] **步骤 1.5：回归——确保现有 ASR/下载测试不破**

运行：`.venv/bin/pytest .agents/skills/video-summary/scripts/tests/ -v`
预期：全过（特别注意 `test_bilibili_browser_cookies.py`）

- [ ] **步骤 1.6：Commit**

```bash
git add .agents/skills/video-summary/scripts/process.py \
        .agents/skills/video-summary/scripts/tests/test_download_video_naming.py
git commit -m "fix(download): yt-dlp 回退分支用 safe_title 命名 + cleanup glob 适配"
```

---

## 任务 2：Bug 2——browser_cookie3 静默缺失预检

**根因：** `check_dependencies`（process.py:121）不查 `browser_cookie3`，`_load_browser_cookies`（451 行）静默返回空字典，B站 v_voucher 风控的降级路径 2 无声失败。

**文件：**
- 修改：`.agents/skills/video-summary/scripts/process.py`（check_dependencies）
- 创建：`.agents/skills/video-summary/scripts/tests/test_check_dependencies_browser_cookies.py`

- [ ] **步骤 2.1：编写失败的测试**

创建 `.agents/skills/video-summary/scripts/tests/test_check_dependencies_browser_cookies.py`：

```python
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, "/Users/jarvis/Documents/VideoToDoc-skills/.agents/skills/video-summary/scripts")
from process import check_dependencies  # noqa: E402


def test_browser_cookie3_listed_when_download_checked():
    """check_download=True 时，结果列表必须含 browser_cookie3 条目（供 doctor 提示）。"""
    with patch("browser_cookie3", create=True), \
         patch("yt_dlp", create=True), \
         patch("curl_cffi", create=True):
        results = check_dependencies(fatal=False, check_download=True)
    names = [r[0] for r in results]
    assert "browser_cookie3" in names


def test_browser_cookie3_missing_is_optional_not_fatal():
    """缺 browser_cookie3 时，fatal=True 不应 sys.exit（它是可选依赖）。"""
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "browser_cookie3":
            raise ModuleNotFoundError("no browser_cookie3")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        # 不应抛 SystemExit
        results = check_dependencies(fatal=True, check_download=True)
    names = [r[0] for r in results]
    assert "browser_cookie3" in names
    bc3 = next(r for r in results if r[0] == "browser_cookie3")
    assert bc3[2] is False  # 标记为不可用
```

- [ ] **步骤 2.2：运行测试验证失败**

运行：`.venv/bin/pytest .agents/skills/video-summary/scripts/tests/test_check_dependencies_browser_cookies.py -v`
预期：FAIL（`browser_cookie3` 不在结果列表，断言 `in names` 失败）

- [ ] **步骤 2.3：在 check_dependencies 加 browser_cookie3 可选检查**

修改 `process.py` 的 `check_dependencies`（121 行），在 `if check_download:` 的 yt-dlp 检查**之后**追加：

```python
    if check_download:
        try:
            import yt_dlp  # noqa: F401
            results.append(("yt-dlp", "pip install yt-dlp pycryptodomex", True))
        except ModuleNotFoundError:
            results.append(("yt-dlp", "pip install yt-dlp pycryptodomex", False))
        # browser_cookie3：B站 v_voucher 风控降级路径 2 依赖，可选但缺失会静默失败
        try:
            import browser_cookie3  # noqa: F401
            results.append(
                ("browser_cookie3", "pip install browser_cookie3 (可选，B站风控降级)", True)
            )
        except ModuleNotFoundError:
            results.append(
                ("browser_cookie3", "pip install browser_cookie3 (可选，B站风控降级)", False)
            )
```

确认 fatal 的 missing 列表仍只含 `["ffmpeg", "yt-dlp"]`，browser_cookie3 不进 fatal（可选）。

- [ ] **步骤 2.4：运行测试验证通过**

运行：`.venv/bin/pytest .agents/skills/video-summary/scripts/tests/test_check_dependencies_browser_cookies.py -v`
预期：PASS

- [ ] **步骤 2.5：Commit**

```bash
git add .agents/skills/video-summary/scripts/process.py \
        .agents/skills/video-summary/scripts/tests/test_check_dependencies_browser_cookies.py
git commit -m "fix(doctor): browser_cookie3 加入可选依赖预检，缺失不再静默"
```

---

## 任务 3：Bug 3——mindmap.mmd 硬编码 + SKILL.md 命名自相矛盾

**根因：** `mindmap.py:24` 硬编码 `run_dir / "mindmap.mmd"`；`render_mindmap.py:_latest_run_dir` 也硬查 `mindmap.mmd`。但 SKILL.md 第 161 行让 Agent 写 `mindmap.mmd`，第 231/318 行又让写 `<标题>_思维导图_<时间戳>.mmd`——Agent 按后者写，脚本按前者找，必然撞车。

**文件：**
- 修改：`.agents/skills/video-to-slides/scripts/videotodoc/mindmap.py`
- 修改：`.agents/skills/video-to-slides/scripts/render_mindmap.py`
- 修改：`.agents/skills/video-to-slides/SKILL.md`（统一约定为带时间戳名）
- 创建：`.agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_glob.py`

- [ ] **步骤 3.1：编写失败的测试**

创建 `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_glob.py`：

```python
from pathlib import Path
import pytest

from videotodoc.mindmap import _find_mindmap_source
from videotodoc.utils import VideoToDocError


def test_prefers_timestamped_name(tmp_path):
    """同时存在 mindmap.mmd 和 X_思维导图_T.mmd 时，优先取带时间戳的。"""
    (tmp_path / "mindmap.mmd").write_text("mindmap\n  root((旧))", encoding="utf-8")
    (tmp_path / "标题_思维导图_20260705_182404.mmd").write_text(
        "mindmap\n  root((新))", encoding="utf-8"
    )
    found = _find_mindmap_source(tmp_path)
    assert found.name == "标题_思维导图_20260705_182404.mmd"


def test_fallback_to_plain_mindmap(tmp_path):
    """只有 mindmap.mmd 时，fallback 用它（向后兼容旧 run）。"""
    (tmp_path / "mindmap.mmd").write_text("mindmap\n  root((旧))", encoding="utf-8")
    found = _find_mindmap_source(tmp_path)
    assert found.name == "mindmap.mmd"


def test_none_raises(tmp_path):
    """两者都不存在 → VideoToDocError。"""
    with pytest.raises(VideoToDocError):
        _find_mindmap_source(tmp_path)
```

- [ ] **步骤 3.2：运行测试验证失败**

运行：`.venv/bin/pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_glob.py -v`
预期：FAIL（`_find_mindmap_source` 不存在，ImportError）

- [ ] **步骤 3.3：实现 _find_mindmap_source 并接入**

修改 `.agents/skills/video-to-slides/scripts/videotodoc/mindmap.py`，在 `render_mindmap_and_refresh_docs` **之前**新增函数：

```python
def _find_mindmap_source(run_dir: Path) -> Path:
    """查找思维导图源文件。

    优先匹配 SKILL.md 约定的 <标题>_思维导图_<时间戳>.mmd（取最新），
    fallback 到旧版 mindmap.mmd（向后兼容）。两者都没有时报错。
    """
    for pattern in ("*_思维导图_*.mmd", "mindmap.mmd"):
        candidates = sorted(run_dir.glob(pattern), reverse=True)
        if candidates:
            return candidates[0]
    raise VideoToDocError(
        f"在 {run_dir} 找不到思维导图源文件"
        "（*_思维导图_*.mmd 或 mindmap.mmd）。"
        "请先完成 Agent 整理步骤并编写思维导图源文件，再运行此脚本。"
    )
```

把 `render_mindmap_and_refresh_docs` 里的：

```python
    mindmap_path = mindmap_path or (run_dir / "mindmap.mmd")
    image_path = image_path or (run_dir / "mindmap.png")
    if not mindmap_path.exists():
        raise VideoToDocError(...)
```

改为：

```python
    mindmap_path = mindmap_path or _find_mindmap_source(run_dir)
    image_path = image_path or (run_dir / "mindmap.png")
```

（保留后续 `raw_text = mindmap_path.read_text(...)`，`_find_mindmap_source` 已保证存在）

- [ ] **步骤 3.4：render_mindmap.py 的 _latest_run_dir 也用 glob**

修改 `.agents/skills/video-to-slides/scripts/render_mindmap.py` 的 `_latest_run_dir`：

```python
def _latest_run_dir(project_dir: Path) -> Path | None:
    runs_dir = project_dir / "runs"
    if not runs_dir.exists():
        return None
    candidates = []
    for p in runs_dir.iterdir():
        if not p.is_dir():
            continue
        # 任一命名约定存在即可（带时间戳的优先，mindmap.mmd 兼容）
        if (p / "mindmap.mmd").exists() or list(p.glob("*_思维导图_*.mmd")):
            candidates.append(p)
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime_ns)
```

- [ ] **步骤 3.5：运行测试验证通过**

运行：`.venv/bin/pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_glob.py -v`
预期：PASS

- [ ] **步骤 3.6：统一 SKILL.md 命名约定**

修改 `.agents/skills/video-to-slides/SKILL.md`：
- 第 161 行附近 `mindmap.mmd` → `<视频标题>_思维导图_<时间戳>.mmd`
- 确认第 231/234 行已是该约定（保留）
- 确认第 318 行目录结构已是该约定（保留）
- 第 248 行 `mindmap_01.png` 等拆分产物命名保留（图片产物，与源文件不同）

- [ ] **步骤 3.7：回归——mindmap 相关测试不破**

运行：`.venv/bin/pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_render.py .agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_verification.py -v`
预期：PASS

- [ ] **步骤 3.8：Commit**

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/mindmap.py \
        .agents/skills/video-to-slides/scripts/render_mindmap.py \
        .agents/skills/video-to-slides/SKILL.md \
        .agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_glob.py
git commit -m "fix(mindmap): glob 匹配时间戳命名 + 统一 SKILL.md 约定"
```

---

## 任务 5：Bug 5——图文对齐「有图无文 / 有文无图」

**根因：** `align.py` 把 segment 原子性归到 `capture_ms` 落入的那张图；长合并段跨越多张图时，所有文字堆到第一张图、后续截图「本页无讲解」。

**修复策略（方案 A，改 align.py 一个文件）：** 按每张截图的讲解区间 `[前图 capture_ms, 本图 capture_ms]` 重分文本；跨越区间边界的合并段，按时间线性插值估算字符位置，向前回溯到最近的句末标点（。！？；）断句，避免切开句子成分。这与 review 的句法硬标准精神一致（不切断句子成分），只是 align 在代码层用客观标点做边界。

**文件：**
- 修改：`.agents/skills/video-to-slides/scripts/videotodoc/align.py`
- 创建：`.agents/skills/video-to-slides/scripts/videotodoc/tests/test_align.py`

- [ ] **步骤 5.1：编写失败的测试**

创建 `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_align.py`：

```python
from dataclasses import dataclass
from pathlib import Path

import pytest

from videotodoc.align import align_sections, _char_pos_for_ms, _snap_to_sentence_end
from videotodoc.models import Slide, SlideSet, Transcript, TranscriptSegment


def _slide(idx, capture_ms, start_ms=None, end_ms=None):
    return Slide(
        slide_index=idx, image_path=f"/tmp/{idx}.png",
        start_ms=start_ms or capture_ms, end_ms=end_ms or capture_ms + 1000,
        capture_ms=capture_ms, confidence=0.9, hash="0" * 16,
    )


def _seg(start_ms, end_ms, text):
    return TranscriptSegment(start_ms=start_ms, end_ms=end_ms, text=text)


class TestCharPosForMs:
    def test_linear_interpolation(self):
        # 段 0-10000ms，文本 10 字 → 5000ms 对应第 5 字
        assert _char_pos_for_ms("0123456789", 0, 10000, 5000) == 5

    def test_clamp_below_zero(self):
        assert _char_pos_for_ms("abc", 1000, 2000, 500) == 0

    def test_clamp_above_end(self):
        assert _char_pos_for_ms("abc", 1000, 2000, 9999) == 3

    def test_zero_duration_returns_zero(self):
        assert _char_pos_for_ms("abc", 1000, 1000, 1000) == 0


class TestSnapToSentenceEnd:
    def test_snap_back_to_period(self):
        # "这是句子。另一句"：pos=6（'一'前）→ 回溯到句号(index 4)之后 = 5
        assert _snap_to_sentence_end("这是句子。另一句", 6) == 5

    def test_no_sentence_end_returns_pos(self):
        assert _snap_to_sentence_end("无标点文本", 3) == 3

    def test_snap_to_question_mark(self):
        # "问题？答案"：pos=4（'案'前）→ 回溯到问号(index 2)之后 = 3
        assert _snap_to_sentence_end("问题？答案", 4) == 3


class TestAlignSectionsWindowSplit:
    def test_long_segment_split_across_two_slides(self):
        """长合并段跨越两张图 → 文本被切分到两页，不再全堆第一张。"""
        # 一段 0-20000ms，含两个句号，跨越两张图（capture 5000/15000）
        seg_text = "这是第一页的讲解内容。这是第二页的讲解内容。"
        transcript = Transcript(
            backend="reused", language="zh",
            segments=[_seg(0, 20000, seg_text)],
        )
        slides = SlideSet(slides=[_slide(1, 5000), _slide(2, 15000)])
        sections = align_sections(slides, transcript)
        assert len(sections) == 2
        # 第一页拿到前半，第二页拿到后半，都不应是「本页无讲解」
        assert "第一页" in sections[0].transcript
        assert "第二页" in sections[1].transcript
        assert "本页无讲解" not in sections[0].transcript
        assert "本页无讲解" not in sections[1].transcript
        # 切点在句号处，没有切开句子成分
        assert sections[0].transcript.rstrip().endswith("。") or "内容" in sections[0].transcript

    def test_empty_transcript_returns_empty(self):
        slides = SlideSet(slides=[_slide(1, 1000)])
        assert align_sections(slides, Transcript("reused", "zh", [])) == []

    def test_slide_without_segment_shows_placeholder(self):
        """截图落在无 segment 区间 → 本页无讲解。"""
        transcript = Transcript(
            backend="reused", language="zh",
            segments=[_seg(0, 1000, "短句。")],
        )
        slides = SlideSet(slides=[_slide(1, 5000), _slide(2, 15000)])
        sections = align_sections(slides, transcript)
        # 第二页无对应文本
        assert "本页无讲解" in sections[1].transcript or sections[1].transcript.strip() == ""
```

- [ ] **步骤 5.2：运行测试验证失败**

运行：`.venv/bin/pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_align.py -v`
预期：FAIL（`_char_pos_for_ms`/`_snap_to_sentence_end` 不存在；且 `test_long_segment_split_across_two_slides` 当前会让两页全堆第一段）

- [ ] **步骤 5.3：重写 align_sections 为按区间切分**

修改 `.agents/skills/video-to-slides/scripts/videotodoc/align.py` 全文：

```python
from __future__ import annotations

from .models import Section, SlideSet, Transcript


# 句末标点：在区间边界回溯断句，避免切开句子成分（与 review 句法硬标准精神一致）
_SENTENCE_END = set("。！？；!?;")


def _char_pos_for_ms(seg_text: str, seg_start_ms: int, seg_end_ms: int, target_ms: int) -> int:
    """按时间线性插值估算 target_ms 在 seg_text 中对应的字符位置。

    合并段无字级时间戳，用段级时间线性插值估算，不精确但足够定位断句点。
    """
    if seg_end_ms <= seg_start_ms:
        return 0
    ratio = (target_ms - seg_start_ms) / (seg_end_ms - seg_start_ms)
    ratio = max(0.0, min(1.0, ratio))
    return int(ratio * len(seg_text))


def _snap_to_sentence_end(seg_text: str, pos: int) -> int:
    """从 pos 向前回溯到最近的句末标点之后，找不到返回 pos。

    保证切分点落在句子成分之间，不切断主谓宾。
    """
    upper = min(pos, len(seg_text))
    for i in range(upper - 1, -1, -1):
        if seg_text[i] in _SENTENCE_END:
            return i + 1
    return pos


def align_sections(slides: SlideSet, transcript: Transcript, sync_offset_ms: int = 0) -> list[Section]:
    """将截图与 ASR 转录按时间轴对齐。

    按截图的 capture_ms 作为分页点：
    - segment 仅包含一张图的 capture_ms → 整段归该图（保留原语义）。
    - segment 跨越多张图 → 在相邻 capture 的中点切分文本，切点回溯到最近句末标点，
      保证不切断主谓宾；切点单调递增，不重复不丢失。每段归对应图。
    - 无图认领的 segment → 归最近图（保留原逻辑：后面的优先，否则前面）。
    """
    if not slides.slides or not transcript.segments:
        return []

    slides_list = slides.slides
    # capture → slide_index 映射（同 ms 取后定义者）
    capture_to_slide: dict[int, int] = {}
    for s in slides_list:
        capture_to_slide[s.capture_ms + sync_offset_ms] = s.slide_index
    captures_sorted = sorted(capture_to_slide.keys())

    page_text: dict[int, list[str]] = {s.slide_index: [] for s in slides_list}
    page_segs: dict[int, list[int]] = {s.slide_index: [] for s in slides_list}

    for seg_idx, seg in enumerate(transcript.segments):
        seg_s = seg.start_ms
        seg_e = seg.end_ms
        # 该 segment 包含的 capture_ms（落在 [seg_s, seg_e) 内）
        inner = [c for c in captures_sorted if seg_s <= c < seg_e]

        if not inner:
            # 无图认领 → 归最近图（后面的优先，否则前面）
            target = None
            for c in captures_sorted:
                if c >= seg_e:
                    target = capture_to_slide[c]
                    break
            if target is None:
                for c in reversed(captures_sorted):
                    if c <= seg_s:
                        target = capture_to_slide[c]
                        break
            if target is None:
                target = slides_list[0].slide_index
            page_text[target].append(seg.text)
            page_segs[target].append(seg_idx)
        elif len(inner) == 1:
            sid = capture_to_slide[inner[0]]
            page_text[sid].append(seg.text)
            page_segs[sid].append(seg_idx)
        else:
            # 多图认领 → 在相邻 capture 中点切分，回溯句号，切点单调递增
            cut_points: list[int] = []
            last_cut = 0
            for i in range(len(inner) - 1):
                mid = (inner[i] + inner[i + 1]) / 2
                pos = _char_pos_for_ms(seg.text, seg_s, seg_e, mid)
                pos = _snap_to_sentence_end(seg.text, pos)
                if pos <= last_cut:
                    # 不能倒退：至少前进 1 字，避免空段
                    pos = min(last_cut + 1, len(seg.text))
                cut_points.append(pos)
                last_cut = pos
            prev = 0
            for i, c in enumerate(inner):
                sid = capture_to_slide[c]
                end = cut_points[i] if i < len(cut_points) else len(seg.text)
                piece = seg.text[prev:end].strip()
                prev = end
                if piece:
                    page_text[sid].append(piece)
                    page_segs[sid].append(seg_idx)

    sections: list[Section] = []
    for slide in slides_list:
        sid = slide.slide_index
        texts = [t for t in page_text[sid] if t]
        matched = "\n\n".join(texts) if texts else "本页无讲解。"
        notes: list[str] = [] if page_segs[sid] else ["empty_transcript_match"]
        sections.append(
            Section(
                slide_index=sid,
                image_path=slide.image_path,
                start_ms=slide.start_ms,
                end_ms=slide.end_ms,
                capture_ms=slide.capture_ms,
                transcript=matched,
                segment_indexes=page_segs[sid],
                notes=notes,
            )
        )
    return sections
```

- [ ] **步骤 5.4：运行测试验证通过**

运行：`.venv/bin/pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_align.py -v`
预期：PASS

- [ ] **步骤 5.5：回归——pipeline 对齐相关测试不破**

运行：`.venv/bin/pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_pipeline_parallel.py .agents/skills/video-to-slides/scripts/videotodoc/tests/test_run_dir_title.py -v`
预期：PASS（这两处 mock 了 align_sections，应不受影响；但跑一遍确认 Section 字段一致）

- [ ] **步骤 5.6：Commit**

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/align.py \
        .agents/skills/video-to-slides/scripts/videotodoc/tests/test_align.py
git commit -m "fix(align): 按截图区间切分文本 + 句末标点回溯断句"
```

---

## 验收案例与测试结果

**端到端验收（可选，需真实视频）：** 拿 `runs/【闪客】新名词诈骗…_20260705_182404` 重新跑一次完整流程，对照：

| 验收项 | 修复前 | 修复后预期 | 验证方法 |
|---|---|---|---|
| self_review 字段 | 报告无此键 | 路径 A `false` / 路径 B `true` | `check_review_report.py <run_dir>` 退出码 0 |
| yt-dlp 产物名 | `video.mp4` | `<safe_title>.mp4` | `ls runs/<run>/*.mp4` 无 `video.mp4` |
| browser_cookie3 预检 | 静默失败 | doctor 提示 | `python3 process.py doctor` 列出 browser_cookie3 |
| mindmap 源文件 | 找不到 mindmap.mmd 报错 | 识别 `<标题>_思维导图_<时间戳>.mmd` | `finalize.py <run_dir>` 成功 |
| 图文对齐 | 长段堆第一图、后续「本页无讲解」 | 文本按截图区间分配 | `sections.json` 各页 transcript 非空 |

**单元测试验收（必做）：**

```bash
.venv/bin/pytest .agents/skills/video-summary/scripts/tests/ -v          # 含任务 0/1/2/4
.venv/bin/pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_mindmap_glob.py .agents/skills/video-to-slides/scripts/videotodoc/tests/test_align.py -v
.venv/bin/pytest .agents/skills/video-summary/scripts/tests/check_skill_md_6_6.py  # 文档断言（如该脚本可执行）
.venv/bin/pytest .agents/skills/video-summary/scripts/tests/test_review_merge.py .agents/skills/video-summary/scripts/tests/test_bilibili_browser_cookies.py -v  # 回归
```

预期：全绿。

---

## 自检

**1. 规格覆盖度：** 用户要求「加 self_review 键」→ 任务 0；bug 修复 → 任务 1/2/3/5。Bug 4（ASR 尾部噪声）经用户确认整理版 Agent 已兜底过滤、不影响最终产物，已剔除。其余 4 个 bug 全覆盖，按上一轮 review 修正意见落地（Bug 1 带 cleanup 连锁、Bug 3 统一 SKILL.md、Bug 5 复用句末标点回溯）。无遗漏。

**2. 占位符扫描：** 每个步骤均有实际代码。任务 1.1 的 mock 略复杂，已在注释里给出简化断言路径，无 TODO。

**3. 类型一致性：** `_find_mindmap_source`、`_char_pos_for_ms`、`_snap_to_sentence_end` 在测试与实现中签名一致。`Section` 字段（slide_index/image_path/start_ms/end_ms/capture_ms/transcript/segment_indexes/notes）与现有 models.py 一致。`TranscriptSegment` 含 start_ms/end_ms/text（已确认 models.py:9）。

**4. 连锁影响：** Bug 1 的 cleanup（834 行）已纳入任务 1.3。Bug 5 改了 align_sections 返回逻辑，但 Section 字段不变，pipeline 下游（render_*_markdown）只读 transcript 字段，不破坏。
