"""Bug 2：browser_cookie3 加入 check_dependencies 预检，缺失不再静默。"""
import builtins
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, "/Users/jarvis/Documents/VideoToDoc-skills/.agents/skills/video-summary/scripts")


def test_browser_cookie3_listed_when_download_checked(monkeypatch):
    """check_download=True 时，结果列表必须含 browser_cookie3 条目（供 doctor 提示）。"""
    for mod in ("browser_cookie3", "yt_dlp", "curl_cffi", "mlx_whisper"):
        monkeypatch.setitem(sys.modules, mod, MagicMock())

    from process import check_dependencies
    results = check_dependencies(fatal=False, check_download=True)
    names = [r[0] for r in results]
    assert "browser_cookie3" in names


def test_browser_cookie3_present_marks_available(monkeypatch):
    """browser_cookie3 可 import 时，标记为可用。"""
    for mod in ("browser_cookie3", "yt_dlp", "curl_cffi", "mlx_whisper"):
        monkeypatch.setitem(sys.modules, mod, MagicMock())

    from process import check_dependencies
    results = check_dependencies(fatal=False, check_download=True)
    bc3 = next(r for r in results if r[0] == "browser_cookie3")
    assert bc3[2] is True


def test_browser_cookie3_missing_is_optional_not_fatal(monkeypatch):
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

    from process import check_dependencies
    # 不应抛 SystemExit
    results = check_dependencies(fatal=True, check_download=True)
    names = [r[0] for r in results]
    assert "browser_cookie3" in names
    bc3 = next(r for r in results if r[0] == "browser_cookie3")
    assert bc3[2] is False  # 标记不可用
