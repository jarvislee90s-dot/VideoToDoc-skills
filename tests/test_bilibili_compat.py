"""B站相关回归测试（自工作区 scripts/tests/ 三份文件迁移合并）。

来源与用例对应：
  - test_bilibili_browser_cookies.py        → _load_browser_cookies / 浏览器 cookies 注入 session
  - test_check_dependencies_browser_cookies.py → check_dependencies 预检 browser_cookie3
  - test_download_video_naming.py           → yt-dlp 回退分支产物命名用 safe_title

迁移要点（第二阶段源适配器重构后）：
  - _load_browser_cookies / _bilibili_get_stream_urls_with_browser_cookies 的真身已搬到
    sources.bilibili（旧 monolith 布局则仍在 process.py）。patch 必须落在被测函数的
    **定义模块** 才生效——这里用双布局 helper 动态定位，patch 不再写死 process；
  - process 级 API（check_dependencies / download_video / _slugify）经 vs_process 夹具
    获取——`import process` 在全量回归中会被 video-to-slides 同名模块污染（见 conftest）；
  - sys.path 注入交给 tests/conftest.py，不写死机器相关绝对路径。
"""

import builtins
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _bilibili_target():
    """双布局定位 B站内部实现的定义模块：新适配器布局 → sources.bilibili；
    旧 monolith 布局（sources.bilibili 不存在）→ process。"""
    try:
        from sources import bilibili as target
    except ImportError:
        import process as target
    return target


# ── 来源：test_bilibili_browser_cookies.py ────────────────────


def test_load_browser_cookies_returns_dict():
    """_load_browser_cookies 应返回浏览器 cookie 字典。"""
    target = _bilibili_target()

    mock_cookie = MagicMock()
    mock_cookie.name = "SESSDATA"
    mock_cookie.value = "abc123"
    mock_cookie.domain = ".bilibili.com"

    with patch("browser_cookie3.chrome", return_value=[mock_cookie]):
        cookies = target._load_browser_cookies("chrome")

    assert cookies.get("SESSDATA") == "abc123"


def test_bilibili_get_stream_urls_with_browser_cookies_uses_browser_cookie(monkeypatch):
    """_bilibili_get_stream_urls_with_browser_cookies 应把浏览器 cookie 注入 curl_cffi session。

    注意 patch 目标是真身定义模块（sources.bilibili / process），
    patch 到兼容 re-export 副本不会生效。
    """
    target = _bilibili_target()
    captured_cookies = {}

    class FakeCookies:
        def set(self, name, value, domain=None):
            captured_cookies[name] = (value, domain)

    class FakeSession:
        def __init__(self, *args, **kwargs):
            self.cookies = FakeCookies()

        def get(self, url, timeout=20, **kwargs):
            resp = MagicMock()
            resp.json.return_value = {"code": -1}
            return resp

    monkeypatch.setattr("curl_cffi.requests.Session", FakeSession)
    monkeypatch.setattr(target, "_load_browser_cookies", lambda b: {"SESSDATA": "abc123"})

    target._bilibili_get_stream_urls_with_browser_cookies("BV1xx", "12345", "chrome")
    assert captured_cookies.get("SESSDATA") == ("abc123", ".bilibili.com")


# ── 来源：test_check_dependencies_browser_cookies.py ──────────


def test_browser_cookie3_listed_when_download_checked(monkeypatch, vs_process):
    """check_download=True 时，结果列表必须含 browser_cookie3 条目（供 doctor 提示）。"""
    for mod in ("browser_cookie3", "yt_dlp", "curl_cffi", "mlx_whisper"):
        monkeypatch.setitem(sys.modules, mod, MagicMock())

    results = vs_process.check_dependencies(fatal=False, check_download=True)
    names = [r[0] for r in results]
    assert "browser_cookie3" in names


def test_browser_cookie3_present_marks_available(monkeypatch, vs_process):
    """browser_cookie3 可 import 时，标记为可用。"""
    for mod in ("browser_cookie3", "yt_dlp", "curl_cffi", "mlx_whisper"):
        monkeypatch.setitem(sys.modules, mod, MagicMock())

    results = vs_process.check_dependencies(fatal=False, check_download=True)
    bc3 = next(r for r in results if r[0] == "browser_cookie3")
    assert bc3[2] is True


def test_browser_cookie3_missing_is_optional_not_fatal(monkeypatch, vs_process):
    """缺 browser_cookie3 时，fatal=True 不应 sys.exit（它是可选依赖）。"""
    for mod in ("yt_dlp", "curl_cffi", "mlx_whisper"):
        monkeypatch.setitem(sys.modules, mod, MagicMock())
    # 让 browser_cookie3 import 失败
    monkeypatch.delitem(sys.modules, "browser_cookie3", raising=False)
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "browser_cookie3":
            raise ModuleNotFoundError("no browser_cookie3")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    # 不应抛 SystemExit
    results = vs_process.check_dependencies(fatal=True, check_download=True)
    names = [r[0] for r in results]
    assert "browser_cookie3" in names
    bc3 = next(r for r in results if r[0] == "browser_cookie3")
    assert bc3[2] is False  # 标记不可用


# ── 来源：test_download_video_naming.py ───────────────────────


def _install_fake_ytdlp(monkeypatch, captured):
    """注入假 yt_dlp 模块：记录 outtmpl 并按其创建产物文件。"""

    class FakeYDL:
        def __init__(self, opts):
            captured["outtmpl"] = opts["outtmpl"]
            captured["opts"] = opts

        def __enter__(self):
            base = captured["outtmpl"].replace("%(ext)s", "mp4")
            Path(base).parent.mkdir(parents=True, exist_ok=True)
            Path(base).write_bytes(b"fake")
            return self

        def __exit__(self, *a):
            return False

        def download(self, urls):
            pass

    fake_mod = types.ModuleType("yt_dlp")
    fake_mod.YoutubeDL = FakeYDL
    monkeypatch.setitem(sys.modules, "yt_dlp", fake_mod)


def test_ytdlp_uses_safe_title_not_video(tmp_path, monkeypatch, vs_process):
    """yt-dlp 回退分支产物名 = safe_title.mp4，不是 video.mp4。

    适配器重构后 download_video 按 URL 派发：youtube URL 命中 sources.youtube
    （yt_dlp_source.download 真身，slugify 语义与 process._slugify 一致）。
    """
    captured: dict = {}
    _install_fake_ytdlp(monkeypatch, captured)

    out = vs_process.download_video(
        "https://www.youtube.com/watch?v=xxxxx",
        run_dir=tmp_path, title="我的标题",
    )

    expected = vs_process._slugify("我的标题") + ".mp4"
    assert out.name == expected, f"期望 {expected}，实际 {out.name}"
    assert out.name != "video.mp4"
    # outtmpl 不能写死 video
    assert "video.%(ext)s" not in captured["outtmpl"]
    # 目录下不应残留 video.mp4
    assert not (tmp_path / "video.mp4").exists()
    # 产物真实存在
    assert (tmp_path / out.name).exists()
