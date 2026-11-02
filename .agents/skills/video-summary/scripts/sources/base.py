"""视频源适配器契约。

每个视频源一个独立模块，process.py 只做统一接入。平台风控策略变化时，
只改对应源模块，不影响其他平台。

两类适配器形态（以 sources/douyin.py、sources/bilibili.py 为参考实现）：

A. 独立下载器形态（平台有自有反爬，不走 yt-dlp）——douyin：
   - matches(url) -> bool
   - probe(url, **opts) -> SourceVideo：解析页面拿元数据与直链（不落盘）；
     video_path 为空 Path()，直链暂存于 metadata["play_url"]
   - download(meta, run_dir) -> SourceVideo：下载到 run_dir 并返回完整 SourceVideo
   - fetch(url, run_dir, **opts) -> SourceVideo：probe + download 便捷封装（独立 CLI 用）
   - has_subtitles = False（跳过平台字幕阶段）

B. yt-dlp 系形态（复用通用 yt-dlp 流水线，可覆盖个别环节）——bilibili / youtube：
   - matches(url) -> bool
   - has_subtitles = True
   - fetch_info(url, proxy=None) -> dict：{"title", "subtitles", "automatic_captions"}
   - fetch_subtitles(url, run_dir, language, info, proxy=None) -> (成功, 文本, 标题)
     （可直接复用 yt_dlp_source.fetch_subtitles）
   - download(url, run_dir, title, proxy=None, cookies_from_browser=None) -> Path

每个源模块同时提供独立 CLI（如适用），便于单独调试：
    python sources/douyin.py <url> --output <mp4路径>
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse


def run_cmd(cmd: list[str], check: bool = True, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=check, timeout=timeout)


def slugify(text: str) -> str:
    """文件系统安全化：Windows 非法字符与控制字符替换为 _（与 process._slugify 同语义）。"""
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', text)
    text = re.sub(r'_+', '_', text).strip('_')
    return text[:80] or "video"


@dataclass
class SourceVideo:
    """源适配器的统一产物。"""

    video_path: Path            # 已下载的视频文件（合流 MP4）
    title: str                  # 视频标题（用于 run 目录命名与摘要）
    source: str = "generic"     # 源标识：douyin / bilibili / youtube / generic
    author: str | None = None
    duration_ms: int | None = None
    has_subtitle: bool = False  # 本源是否有平台字幕可取（决定 process.py 是否走字幕阶段）
    metadata: dict = field(default_factory=dict)


def normalize_url(url: str) -> str:
    """去掉首尾空白与包裹文本，返回纯 URL。紧贴 URL 的中文视为分享文本尾巴，一并剥离。"""
    url = url.strip().strip('"\'')
    m = re.search(r"https?://\S+", url)
    if not m:
        return url
    matched = m.group(0)
    # 抖音 URL 本身不含中文；尾部 CJK/中文标点按"用户粘贴文本粘连"处理
    matched = re.sub(r"[\u4e00-\u9fff\u3000-\u303f\uff01-\uff5e\u2018-\u201d,.;：；！？，。]+$", "", matched)
    return matched


def is_short_link(url: str) -> bool:
    """v.douyin.com/xxx 等分享短链，需 302 解析后再判断平台。"""
    host = urlparse(url).netloc.lower()
    return any(host == h or host.endswith("." + h) for h in ("v.douyin.com", "iesdouyin.com"))


def source_cli_main(result: SourceVideo) -> None:
    """源模块独立 CLI 的统一收尾：打印 JSON 结果行供调用方解析。"""
    print(json.dumps({
        "video_path": str(result.video_path.resolve()),
        "title": result.title,
        "source": result.source,
        "author": result.author,
        "duration_ms": result.duration_ms,
        "metadata": result.metadata,
    }, ensure_ascii=False))
