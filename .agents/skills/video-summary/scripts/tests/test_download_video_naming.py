"""Bug 1：yt-dlp 回退分支产物名必须用 safe_title，不能写死 video.mp4。"""
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, "/Users/jarvis/Documents/VideoToDoc-skills/.agents/skills/video-summary/scripts")


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


def test_ytdlp_uses_safe_title_not_video(tmp_path, monkeypatch):
    """yt-dlp 回退分支产物名 = safe_title.mp4，不是 video.mp4。"""
    captured: dict = {}
    _install_fake_ytdlp(monkeypatch, captured)

    from process import download_video, _slugify  # noqa: E402

    out = download_video(
        "https://www.youtube.com/watch?v=xxxxx",
        run_dir=tmp_path, title="我的标题",
    )

    expected = _slugify("我的标题") + ".mp4"
    assert out.name == expected, f"期望 {expected}，实际 {out.name}"
    assert out.name != "video.mp4"
    # outtmpl 不能写死 video
    assert "video.%(ext)s" not in captured["outtmpl"]
    # 目录下不应残留 video.mp4
    assert not (tmp_path / "video.mp4").exists()
    # 产物真实存在
    assert (tmp_path / out.name).exists()
