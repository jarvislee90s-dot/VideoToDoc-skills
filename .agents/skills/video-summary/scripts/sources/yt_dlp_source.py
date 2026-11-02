"""通用 yt-dlp 源适配器：信息获取 / 字幕获取 / 下载。

yt-dlp 系适配器（bilibili / youtube）的默认实现，也是未识别 URL 的兜底。
函数体与原 process.py 中的实现保持一致（battle-tested），仅做模块化搬家。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    from .base import run_cmd, slugify
except ImportError:  # 独立直跑时无包上下文
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from base import run_cmd, slugify  # noqa: E402

# 与 douyin 适配器共用同一 UA 语义；yt-dlp 自带 UA 处理，这里只用于直链兜底场景
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36")

has_subtitles = True


def matches(url: str) -> bool:
    """兜底适配器：任何 URL 都接受（注册表中排在最后）。"""
    return True


# ── 信息获取 ────────────────────────────────────────────────


def fetch_info(url: str, proxy: str | None = None) -> dict:
    """获取视频信息（标题、字幕列表等），纯 yt-dlp 路径。"""
    import yt_dlp

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["zh-Hans", "zh", "zh-CN", "en"],
    }
    if proxy:
        ydl_opts["proxy"] = proxy

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    title = info.get("title", "video")
    subtitles = info.get("subtitles", {})
    auto_captions = info.get("automatic_captions", {})

    print(f"  📺 标题：{title}")
    print(f"  🔤 人工字幕：{list(subtitles.keys()) or '无'}")
    print(f"  🤖 自动字幕：{list(auto_captions.keys()) or '无'}")

    return {
        "title": title,
        "subtitles": subtitles,
        "automatic_captions": auto_captions,
    }


# ── 字幕获取 ────────────────────────────────────────────────


def _download_subtitle(url: str, subtitle_list: list, run_dir: Path, title: str, sub_type: str,
                       proxy: str | None = None) -> tuple[bool, str | None, str | None]:
    """下载并解析字幕文件"""
    import yt_dlp

    format_priority = {"srv1": 1, "srt": 2, "vtt": 3}
    sorted_subs = sorted(subtitle_list, key=lambda s: format_priority.get(s.get("ext", ""), 99))
    sub_info = sorted_subs[0]

    print(f"  📥 下载 {sub_type}：{sub_info.get('name', '未知语言')} ({sub_info.get('ext', '未知格式')})")

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "writesubtitles": True,
        # 自动字幕必须显式开启，否则 yt-dlp 不落任何文件（历史 bug：自动字幕永远下载失败）
        "writeautomaticsub": sub_type == "自动字幕",
        "subtitlesformat": "srv1/srt/vtt",
        "subtitleslangs": [sub_info.get("language_code", "zh")],
        "outtmpl": str(run_dir / "subtitle"),
    }
    if proxy:
        ydl_opts["proxy"] = proxy

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        # 字幕失败不应中断整次运行：打印警告后回退 ASR
        print(f"  ⚠️  字幕下载失败：{e}")
        return False, None, title

    subtitle_path = None
    for f in run_dir.glob("subtitle*"):
        if f.suffix in [".srv1", ".srt", ".vtt"]:
            subtitle_path = f
            break

    if not subtitle_path or not subtitle_path.exists():
        return False, None, title

    text, segments = _parse_subtitle_file(subtitle_path)
    subtitle_path.unlink(missing_ok=True)

    if text:
        seg_cache = run_dir / "_subtitle_segments.json"
        seg_cache.write_text(json.dumps(segments, ensure_ascii=False, indent=2), encoding="utf-8")
        return True, text, title

    return False, None, title


def _parse_subtitle_file(path: Path) -> tuple[str | None, list[dict]]:
    """解析字幕文件为纯文本 + 带 start_ms/end_ms 的 segment 列表。

    支持 SRT、VTT（含 --> 时间戳行）和 XML 格式。
    """
    import re

    text = path.read_text(encoding="utf-8")
    lines_list: list[str] = []
    segments: list[dict] = []

    # SRT / VTT 格式：包含 --> 时间戳行
    if "-->" in text:
        # 按空行分块
        blocks = re.split(r"\n\s*\n", text.strip())
        for block in blocks:
            block_lines = block.strip().split("\n")
            # 找时间戳行
            tc_line = None
            text_lines: list[str] = []
            for line in block_lines:
                if "-->" in line:
                    tc_line = line
                elif line.strip() and not line.strip().isdigit():
                    # 跳过 WEBVTT 头
                    if not line.strip().startswith("WEBVTT"):
                        text_lines.append(line.strip())
            if tc_line and text_lines:
                m = re.match(
                    r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)",
                    tc_line,
                )
                if m:
                    g = m.groups()
                    start_ms = int(int(g[0]) * 3600000 + int(g[1]) * 60000 + int(g[2]) * 1000 + int(g[3]))
                    end_ms = int(int(g[4]) * 3600000 + int(g[5]) * 60000 + int(g[6]) * 1000 + int(g[7]))
                    seg_text = " ".join(text_lines)
                    lines_list.append(seg_text)
                    segments.append({"start_ms": start_ms, "end_ms": end_ms, "text": seg_text})
        if lines_list:
            return "\n".join(lines_list), segments

    # XML 格式
    if "<text" in text or "<p" in text:
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(text)
            for elem in root.iter():
                if elem.text and elem.text.strip():
                    start_attr = elem.get("start")
                    dur_attr = elem.get("dur")
                    start_ms = int(float(start_attr) * 1000) if start_attr else 0
                    end_ms = start_ms + int(float(dur_attr) * 1000) if (start_ms is not None and dur_attr) else start_ms
                    lines_list.append(elem.text.strip())
                    segments.append({"start_ms": start_ms, "end_ms": end_ms, "text": elem.text.strip()})
        except ET.ParseError:
            pass
        if lines_list:
            return "\n".join(lines_list), segments

    # 纯文本兜底
    for line in text.splitlines():
        line = line.strip()
        if not line or line.isdigit():
            continue
        if "-->" in line or line.startswith("WEBVTT"):
            continue
        if line:
            lines_list.append(line)
            segments.append({"start_ms": 0, "end_ms": 0, "text": line})

    return "\n".join(lines_list) if lines_list else None, segments


def fetch_subtitles(url: str, run_dir: Path, language: str = "zh", info: dict | None = None,
                    proxy: str | None = None) -> tuple[bool, str | None, str | None]:
    """获取平台字幕，返回 (成功, 字幕文本, 视频标题)"""
    try:
        if info is None:
            info = fetch_info(url, proxy)
    except Exception as e:
        print(f"  ⚠️  获取视频信息失败：{e}")
        return False, None, None

    title = info.get("title", "video")
    subtitles = info.get("subtitles", {})
    auto_captions = info.get("automatic_captions", {})

    lang_priority = ["zh-Hans", "zh", "zh-CN", "en"]
    for lang in lang_priority:
        if lang in subtitles and subtitles[lang]:
            return _download_subtitle(url, subtitles[lang], run_dir, title, "人工字幕", proxy)
        if lang in auto_captions and auto_captions[lang]:
            return _download_subtitle(url, auto_captions[lang], run_dir, title, "自动字幕", proxy)

    for key in list(subtitles.keys()):
        if key.startswith("zh") or key.startswith("en"):
            return _download_subtitle(url, subtitles[key], run_dir, title, "人工字幕", proxy)

    for key in list(auto_captions.keys()):
        if key.startswith("zh") or key.startswith("en"):
            return _download_subtitle(url, auto_captions[key], run_dir, title, "自动字幕", proxy)

    return False, None, title


# ── 下载 ────────────────────────────────────────────────────


def _prefetch_cookies_for_yt_dlp(site_url: str, run_dir: Path) -> str | None:
    """用 curl_cffi 先访问目标站点获取指纹 cookies，写入 Netscape cookie 文件供 yt-dlp 使用。"""
    try:
        from curl_cffi import requests as cffi_requests
        s = cffi_requests.Session(impersonate="chrome")
        s.get(site_url, timeout=15)
        if not s.cookies:
            return None
        cookie_file = run_dir / "_prefetched.cookies"
        with open(cookie_file, "w") as f:
            f.write("# Netscape HTTP Cookie File\n")
            for c in s.cookies:
                secure = "TRUE" if getattr(c, "secure", False) else "FALSE"
                domain = getattr(c, "domain", "") or ".xiaohongshu.com"
                path = getattr(c, "path", "/") or "/"
                expires = str(int(getattr(c, "expires", 0)) or 0)
                f.write(f"{domain}\tTRUE\t{path}\t{secure}\t{expires}\t{c.name}\t{c.value}\n")
        return str(cookie_file)
    except Exception:
        return None


def download(url: str, run_dir: Path, title: str | None = None, proxy: str | None = None,
             cookies_from_browser: str | None = None) -> Path:
    """通用 yt-dlp 下载（未识别平台兜底路径）。"""
    import yt_dlp

    safe_title = slugify(title or "video")
    print(f"  ⬇️  下载视频（yt-dlp）...")
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "outtmpl": str(run_dir / f"{safe_title}.%(ext)s"),
        "merge_output_format": "mp4",
    }
    if proxy:
        ydl_opts["proxy"] = proxy
    if cookies_from_browser:
        ydl_opts["cookiesfrombrowser"] = (cookies_from_browser,)
    if (not cookies_from_browser) and ("xiaohongshu" in url or "xhslink" in url):
        # cookiefile 与 cookiesfrombrowser 在 yt-dlp 里互斥，显式 cookie 来源优先
        prefetched = _prefetch_cookies_for_yt_dlp("https://www.xiaohongshu.com/", run_dir)
        if prefetched:
            ydl_opts["cookiefile"] = prefetched

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        msg = str(e)
        hint = ""
        if "cookie database" in msg.lower() or "permission denied" in msg.lower():
            hint = "（提示：浏览器 cookie 库被锁或无权限——关闭浏览器后重试，或换 --cookies-from-browser 来源）"
        raise RuntimeError(f"yt-dlp 下载失败：{msg}{hint}") from e

    for ext in ["mp4", "webm", "mkv", "mov"]:
        candidate = run_dir / f"{safe_title}.{ext}"
        if candidate.exists():
            if ext != "mp4":
                mp4_path = run_dir / f"{safe_title}.mp4"
                candidate.rename(mp4_path)
                return mp4_path
            return candidate

    raise RuntimeError("视频下载后找不到文件")
