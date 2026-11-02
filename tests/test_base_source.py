"""sources/base.py 的单元测试：适配器契约（normalize_url / SourceVideo / is_short_link）。

全部为纯函数测试，不涉及网络与浏览器。
"""

from sources import base as base_source


# ── normalize_url：包裹文本提取 URL、去引号、去尾部标点 ──────────


def test_normalize_url_strips_surrounding_whitespace():
    assert base_source.normalize_url("  https://v.douyin.com/abc  \n") == "https://v.douyin.com/abc"


def test_normalize_url_strips_wrapping_quotes():
    assert base_source.normalize_url('"https://www.douyin.com/video/123"') == "https://www.douyin.com/video/123"
    assert base_source.normalize_url("'https://v.douyin.com/abc'") == "https://v.douyin.com/abc"


def test_normalize_url_extracts_url_from_wrapped_text():
    text = "看这个视频 https://v.douyin.com/abc 很有意思"
    assert base_source.normalize_url(text) == "https://v.douyin.com/abc"


def test_normalize_url_removes_trailing_cjk_and_ascii_punctuation():
    assert base_source.normalize_url("https://v.douyin.com/abc。") == "https://v.douyin.com/abc"
    assert base_source.normalize_url("https://www.douyin.com/video/123,.;") == "https://www.douyin.com/video/123"
    assert base_source.normalize_url("地址：https://v.douyin.com/abc，。") == "https://v.douyin.com/abc"


def test_normalize_url_keeps_text_without_url_unchanged():
    text = "这里没有链接的普通文本"
    assert base_source.normalize_url(text) == text


# ── SourceVideo：字段默认值与 metadata 默认工厂 ─────────────────


def test_source_video_default_values():
    from pathlib import Path

    sv = base_source.SourceVideo(video_path=Path("video.mp4"), title="标题")
    assert sv.source == "generic"
    assert sv.author is None
    assert sv.duration_ms is None
    assert sv.has_subtitle is False
    assert sv.metadata == {}


def test_source_video_metadata_default_factory_is_per_instance():
    from pathlib import Path

    sv1 = base_source.SourceVideo(video_path=Path("a.mp4"), title="a")
    sv2 = base_source.SourceVideo(video_path=Path("b.mp4"), title="b")
    sv1.metadata["play_url"] = "https://cdn/x.mp4"
    assert sv2.metadata == {}, "metadata 应使用 default_factory，实例间不共享同一 dict"


# ── is_short_link：v.douyin.com / iesdouyin.com 判断 ────────────


def test_is_short_link_true_for_v_douyin_share_link():
    assert base_source.is_short_link("https://v.douyin.com/iAbCdEf/") is True


def test_is_short_link_true_for_iesdouyin_and_subdomains():
    assert base_source.is_short_link("https://iesdouyin.com/share/video/1") is True
    assert base_source.is_short_link("https://www.iesdouyin.com/share/video/1") is True


def test_is_short_link_false_for_standard_douyin_page():
    assert base_source.is_short_link("https://www.douyin.com/video/7123456789012345678") is False


def test_is_short_link_false_for_other_platforms_and_bare_host():
    assert base_source.is_short_link("https://www.bilibili.com/video/BV1xx411c7mD") is False
    assert base_source.is_short_link("https://www.youtube.com/watch?v=abc") is False
    assert base_source.is_short_link("https://notdouyin.com/video/1") is False
