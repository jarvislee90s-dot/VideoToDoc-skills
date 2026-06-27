"""共享工具函数测试：slugify、format_ms、format_seconds。"""
from __future__ import annotations

import pytest
from text_utils import slugify, format_ms, format_seconds


class TestSlugify:
    def test_slugify_preserves_chinese(self):
        """slugify 应保留中文字符。"""
        result = slugify("深度学习入门教程")
        assert result == "深度学习入门教程"

    def test_slugify_replaces_illegal_chars(self):
        """slugify 应替换文件系统非法字符为下划线。"""
        result = slugify('a/b:c*d?e"f<g>h|i\\j')
        assert "/" not in result
        assert ":" not in result
        assert "*" not in result
        assert "?" not in result
        assert '"' not in result
        assert "<" not in result
        assert ">" not in result
        assert "|" not in result
        assert "\\" not in result

    def test_slugify_replaces_spaces(self):
        """slugify 应将空白符替换为下划线。"""
        result = slugify("hello world  test")
        assert " " not in result
        assert "_" in result

    def test_slugify_strips_leading_trailing_underscores(self):
        """slugify 应去除首尾下划线。"""
        result = slugify("___hello___")
        assert result == "hello"

    def test_slugify_merges_multiple_underscores(self):
        """slugify 应合并连续下划线。"""
        result = slugify("a   b   c")
        assert "__" not in result

    def test_slugify_empty_returns_video(self):
        """空字符串或纯非法字符应返回 'video'。"""
        assert slugify("") == "video"
        assert slugify("///") == "video"
        assert slugify("   ") == "video"

    def test_slugify_preserves_dots_and_hyphens(self):
        """slugify 应保留点号和连字符。"""
        result = slugify("my-video.file_v1")
        assert result == "my-video.file_v1"

    def test_slugify_max_len(self):
        """slugify 应截断到 max_len 长度。"""
        long_name = "a" * 200
        result = slugify(long_name, max_len=50)
        assert len(result) == 50

    def test_slugify_mixed_chinese_english(self):
        """slugify 应正确处理中英文混合。"""
        result = slugify("第3讲：Python 基础语法")
        assert "第3讲" in result
        assert "Python" in result
        assert "基础语法" in result


class TestFormatMs:
    def test_format_ms_zero(self):
        assert format_ms(0) == "00:00"

    def test_format_ms_seconds_only(self):
        assert format_ms(5000) == "00:05"
        assert format_ms(59000) == "00:59"

    def test_format_ms_minutes(self):
        assert format_ms(60000) == "01:00"
        assert format_ms(90000) == "01:30"

    def test_format_ms_hours(self):
        assert format_ms(3600000) == "01:00:00"
        assert format_ms(3661000) == "01:01:01"

    def test_format_ms_negative_clamped_to_zero(self):
        assert format_ms(-1000) == "00:00"


class TestFormatSeconds:
    def test_format_seconds_zero(self):
        assert format_seconds(0) == "00:00"

    def test_format_seconds_basic(self):
        assert format_seconds(5) == "00:05"
        assert format_seconds(60) == "01:00"
        assert format_seconds(3600) == "01:00:00"

    def test_format_negative_returns_unknown(self):
        assert format_seconds(-1) == "??:??"
        assert format_seconds(None) == "??:??"

    def test_format_seconds_float(self):
        assert format_seconds(1.5) == "00:01"
        assert format_seconds(90.5) == "01:30"
        assert format_seconds(91.0) == "01:31"
