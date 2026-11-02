"""YouTube 源适配器（yt-dlp 系形态，薄封装）。

YouTube 走标准 yt-dlp 流水线，与通用实现一致；通常需要代理
（--proxy 或 VIDEO_SUMMARY_PROXY_MAP），由 process.py 统一透传。
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlparse

try:
    from . import yt_dlp_source
except ImportError:  # 独立直跑时无包上下文（与其他源模块保持一致）
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import yt_dlp_source  # noqa: E402

has_subtitles = True

YOUTUBE_HOSTS = ("youtube.com", "youtu.be", "youtube-nocookie.com")


def matches(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    host = host.removeprefix("www.")
    return any(host == h or host.endswith("." + h) for h in YOUTUBE_HOSTS)


# 信息/字幕/下载与通用实现一致
fetch_info = yt_dlp_source.fetch_info
fetch_subtitles = yt_dlp_source.fetch_subtitles
download = yt_dlp_source.download
