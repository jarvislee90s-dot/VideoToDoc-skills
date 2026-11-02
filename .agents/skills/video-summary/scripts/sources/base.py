"""视频源适配器契约。

每个视频源一个独立模块，process.py 只做统一接入。平台风控策略变化时，
只改对应源模块，不影响其他平台。

适配器需实现：
- matches(url) -> bool：是否属于本源
- resolve(url) -> SourceVideo：解析并下载视频到 run_dir

每个源模块同时提供独立 CLI，便于单独调试：
    python sources/douyin.py <url> --output <mp4路径>
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse


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
