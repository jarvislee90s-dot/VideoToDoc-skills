"""Bug 3：mindmap 源文件查找优先匹配时间戳命名，fallback 到 mindmap.mmd。"""
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


def test_multiple_timestamped_takes_latest(tmp_path):
    """多个时间戳命名时，取字典序最大的（最新时间戳）。"""
    (tmp_path / "标题_思维导图_20260701_100000.mmd").write_text("a", encoding="utf-8")
    (tmp_path / "标题_思维导图_20260705_182404.mmd").write_text("b", encoding="utf-8")
    found = _find_mindmap_source(tmp_path)
    assert found.name == "标题_思维导图_20260705_182404.mmd"
