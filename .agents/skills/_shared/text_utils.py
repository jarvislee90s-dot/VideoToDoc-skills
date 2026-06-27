from __future__ import annotations

import re


def slugify(name: str, max_len: int = 80) -> str:
    """把字符串转为安全的文件名/目录名，保留中文字符。

    - 替换文件系统非法字符、空白符等为下划线
    - 保留中文、字母、数字、点、下划线、连字符
    - 合并连续下划线
    - 去除首尾下划线和点
    - 截断到 max_len 长度
    """
    cleaned = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", name, flags=re.UNICODE)
    cleaned = re.sub(r"_+", "_", cleaned).strip("._")
    return cleaned[:max_len] or "video"


def format_ms(ms: int) -> str:
    """毫秒转换为 HH:MM:SS 或 MM:SS 格式。"""
    seconds = max(0, int(ms)) // 1000
    minutes, sec = divmod(seconds, 60)
    hours, minute = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minute:02d}:{sec:02d}"
    return f"{minute:02d}:{sec:02d}"


def format_seconds(sec: float) -> str:
    """秒转换为 HH:MM:SS 或 MM:SS 格式。"""
    if sec is None or sec < 0:
        return "??:??"
    return format_ms(int(round(float(sec) * 1000)))
