#!/usr/bin/env python3
"""video-summary: 视频 URL 或本地文件 → 下载 + 字幕/ASR → 摘要

流程：
  URL  → 获取字幕（优先）→ 有字幕直接保存 → 无字幕下载视频 → ASR
  本地 → 提取音频 → ASR → transcript.txt

产物命名：
  runs/<视频标题>_<时间戳>/
    ├── <视频标题>_总结_<时间戳>.md   # 最终摘要
    ├── transcript.json
    ├── transcript.txt
    └── video.mp4（如需ASR）
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

# ── 站点代理映射 ──────────────────────────────────────────────

SITE_PROXY_MAP: dict[str, str] = {}

_env_proxy = os.environ.get("VIDEO_SUMMARY_PROXY_MAP", "") or os.environ.get("VIDEO_TO_NOTES_PROXY_MAP", "")
if _env_proxy:
    for entry in _env_proxy.split(";"):
        if ":" in entry:
            _domain, _proxy = entry.split(":", 1)
            SITE_PROXY_MAP[_domain.strip()] = f"http://{_proxy.strip()}"


# ── 工具函数 ──────────────────────────────────────────────────


def _get_proxy_for_url(url: str, user_proxy: str | None = None) -> str | None:
    if user_proxy is not None:
        return user_proxy
    for domain, proxy in SITE_PROXY_MAP.items():
        if domain in url:
            return proxy
    return None


def _slugify(text: str) -> str:
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', text)
    text = re.sub(r'_+', '_', text).strip('_')
    return text[:80] or "video"


def _short_hash(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()[:12]


def _format_seconds(s: float) -> str:
    if s is None or s < 0:
        return "??:??"
    m, sec = divmod(int(s), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


def _format_bytes(n: float) -> str:
    if n is None or n <= 0:
        return "??"
    for unit in ["B", "KiB", "MiB", "GiB"]:
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TiB"


def run_cmd(cmd: list[str], check: bool = True, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=check, timeout=timeout)


def _is_url(text: str) -> bool:
    return text.startswith("http://") or text.startswith("https://")


def _is_bilibili_url(url: str) -> bool:
    return "bilibili.com" in url or "b23.tv" in url


def _timestamp() -> str:
    """生成时间戳，格式：YYYYMMDD_HHMMSS"""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _build_run_dir_name(title: str, user_input: str) -> str:
    """构建 run 目录名称：视频标题_时间戳"""
    slug = _slugify(title)
    ts = _timestamp()
    return f"{slug}_{ts}"


def _build_summary_filename(title: str, ts: str) -> str:
    """构建最终摘要文件名：视频标题_总结_时间戳.md"""
    slug = _slugify(title)
    return f"{slug}_总结_{ts}.md"


# ── 依赖检查 & 诊断 ─────────────────────────────────────────


def check_dependencies(fatal: bool = True, check_asr: bool = False, check_download: bool = False) -> list[tuple[str, str, bool]]:
    """检查依赖，返回 [(名称, 安装命令, 是否可用)] 列表"""
    results = []

    try:
        run_cmd(["ffmpeg", "-version"])
        results.append(("ffmpeg", "brew install ffmpeg (macOS) / apt install ffmpeg (Linux)", True))
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        results.append(("ffmpeg", "brew install ffmpeg (macOS) / apt install ffmpeg (Linux)", False))

    if check_download:
        try:
            import yt_dlp  # noqa: F401
            results.append(("yt-dlp", "pip install yt-dlp pycryptodomex", True))
        except ModuleNotFoundError:
            results.append(("yt-dlp", "pip install yt-dlp pycryptodomex", False))

    if check_asr:
        try:
            import mlx_whisper  # noqa: F401
            results.append(("mlx-whisper", "pip install mlx-whisper", True))
        except (ModuleNotFoundError, RuntimeError) as e:
            results.append(("mlx-whisper", f"pip install mlx-whisper（当前不可用：{type(e).__name__}）", False))

    try:
        from curl_cffi import requests as _  # noqa: F401
        results.append(("curl_cffi", "pip install curl_cffi (可选)", True))
    except ModuleNotFoundError:
        results.append(("curl_cffi", "pip install curl_cffi (可选，用于B站)", False))

    if fatal:
        missing = [(n, c) for n, c, ok in results if not ok and n in ["ffmpeg", "yt-dlp"]]
        if missing:
            print("❌ 缺少必需依赖：\n")
            for name, cmd in missing:
                print(f"  {name}: {cmd}")
            sys.exit(1)

    return results


def cmd_doctor() -> None:
    """诊断依赖和配置状态"""
    print("🔍 video-summary 诊断\n")
    results = check_dependencies(fatal=False, check_asr=True, check_download=True)
    for name, cmd, ok in results:
        status = "✅" if ok else "❌"
        print(f"  {status} {name}")
        if not ok:
            print(f"     安装：{cmd}")


# ── 字幕获取 ────────────────────────────────────────────────


def fetch_video_info(url: str, proxy: str | None = None) -> dict:
    """获取视频信息（标题、字幕列表等）"""
    import yt_dlp

    # B站：优先用 curl_cffi 绕过 412
    if _is_bilibili_url(url):
        try:
            from curl_cffi import requests as _  # noqa: F401
            bvid, cid, title = _bilibili_extract_ids(url)
            if title:
                # 检查字幕（通过 player/v2 API）
                subtitles: dict = {}
                auto_captions: dict = {}
                if bvid and cid:
                    try:
                        from curl_cffi import requests as cffi_requests
                        resp = cffi_requests.get(
                            "https://api.bilibili.com/x/player/v2",
                            params={"bvid": bvid, "cid": cid},
                            impersonate="chrome", timeout=15,
                        )
                        sub_data = resp.json().get("data", {}).get("subtitle", {})
                        for s in sub_data.get("subtitles", []):
                            lang = s.get("lan", "unknown")
                            subtitles.setdefault(lang, []).append({
                                "ext": "json",
                                "url": s.get("subtitle_url", ""),
                                "language_code": lang,
                                "name": s.get("lan_doc", lang),
                            })
                    except Exception:
                        pass
                print(f"  📺 标题：{title}")
                print(f"  🔤 人工字幕：{list(subtitles.keys()) or '无'}")
                print(f"  🤖 自动字幕：{list(auto_captions.keys()) or '无'}")
                return {"title": title, "subtitles": subtitles, "automatic_captions": auto_captions}
        except Exception:
            pass  # fallback to yt-dlp

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


def _download_subtitle(url: str, subtitle_list: list, run_dir: Path, title: str, sub_type: str) -> tuple[bool, str | None, str | None]:
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
        "subtitlesformat": "srv1/srt/vtt",
        "subtitleslangs": [sub_info.get("language_code", "zh")],
        "outtmpl": str(run_dir / "subtitle"),
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

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
    """解析字幕文件为纯文本"""
    text = path.read_text(encoding="utf-8")
    lines = []
    segments = []

    if "<text" in text or "<p" in text:
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(text)
            for elem in root.iter():
                if elem.text and elem.text.strip():
                    lines.append(elem.text.strip())
                    segments.append({"text": elem.text.strip(), "start": None, "end": None})
        except ET.ParseError:
            pass

    if not lines:
        for line in text.splitlines():
            line = line.strip()
            if not line or line.isdigit():
                continue
            if "-->" in line or line.startswith("WEBVTT"):
                continue
            if line:
                lines.append(line)
                segments.append({"text": line, "start": None, "end": None})

    return "\n".join(lines) if lines else None, segments


def fetch_subtitles(url: str, run_dir: Path, language: str = "zh") -> tuple[bool, str | None, str | None]:
    """获取平台字幕，返回 (成功, 字幕文本, 视频标题)"""
    import yt_dlp

    try:
        info = fetch_video_info(url)
    except Exception as e:
        print(f"  ⚠️  获取视频信息失败：{e}")
        return False, None, None

    title = info.get("title", "video")
    subtitles = info.get("subtitles", {})
    auto_captions = info.get("automatic_captions", {})

    lang_priority = ["zh-Hans", "zh", "zh-CN", "en"]
    for lang in lang_priority:
        if lang in subtitles and subtitles[lang]:
            return _download_subtitle(url, subtitles[lang], run_dir, title, "人工字幕")
        if lang in auto_captions and auto_captions[lang]:
            return _download_subtitle(url, auto_captions[lang], run_dir, title, "自动字幕")

    for key in list(subtitles.keys()):
        if key.startswith("zh") or key.startswith("en"):
            return _download_subtitle(url, subtitles[key], run_dir, title, "人工字幕")

    for key in list(auto_captions.keys()):
        if key.startswith("zh") or key.startswith("en"):
            return _download_subtitle(url, auto_captions[key], run_dir, title, "自动字幕")

    return False, None, title


# ── 视频下载 ────────────────────────────────────────────────


def _bilibili_detect_v_voucher(data: dict) -> bool:
    """检测 playurl 返回是否为 v_voucher 风控（无真实视频流）。"""
    if data.get("code") != 0:
        return False
    d = data.get("data", {})
    return "v_voucher" in d and "dash" not in d and "durl" not in d


def _bilibili_get_stream_urls_with_cookies(bvid: str, cid: str) -> tuple[str | None, str | None, bool]:
    """带 buvid cookies 调 playurl。返回 (video_url, audio_url, is_v_voucher)。"""
    from curl_cffi import requests as cffi_requests

    s = cffi_requests.Session(impersonate="chrome")
    # 注入 buvid cookies
    try:
        fr = s.get("https://api.bilibili.com/x/frontend/finger/spi", timeout=20).json()
        s.cookies.set("buvid3", fr["data"]["b_3"], domain=".bilibili.com")
        s.cookies.set("buvid4", fr["data"]["b_4"], domain=".bilibili.com")
    except Exception:
        pass
    s.get(f"https://www.bilibili.com/video/{bvid}", timeout=20)

    resp = s.get(
        "https://api.bilibili.com/x/player/wbi/playurl",
        params={"bvid": bvid, "cid": cid, "fnval": 4048, "fnver": 0, "fourk": 1, "qn": 80},
        timeout=30,
    )
    data = resp.json()
    if _bilibili_detect_v_voucher(data):
        return None, None, True
    if data.get("code") != 0:
        return None, None, False
    d = data["data"]
    if "dash" in d:
        dash = d["dash"]
        videos = dash.get("video", [])
        audios = dash.get("audio", [])
        best_video = max(videos, key=lambda v: v.get("height", 0) * v.get("width", 0)) if videos else None
        best_audio = audios[0] if audios else None
        v_url = best_video.get("baseUrl") or best_video.get("base_url") if best_video else None
        a_url = best_audio.get("baseUrl") or best_audio.get("base_url") if best_audio else None
        return v_url, a_url, False
    elif "durl" in d:
        durls = d["durl"]
        return (durls[0]["url"] if durls else None), None, False
    return None, None, False


def _bilibili_get_stream_urls(bvid: str, cid: str) -> tuple[str | None, str | None]:
    """通过 curl_cffi 直接调用 B站 playurl API 获取视频/音频流 URL
    返回 (video_url, audio_url)，DASH 格式分离
    """
    from curl_cffi import requests as cffi_requests

    resp = cffi_requests.get(
        "https://api.bilibili.com/x/player/wbi/playurl",
        params={"bvid": bvid, "cid": cid, "fnval": 4048, "fnver": 0, "fourk": 1, "qn": 80},
        impersonate="chrome",
        timeout=30,
    )
    data = resp.json()
    if data.get("code") != 0:
        return None, None

    d = data["data"]
    if "dash" in d:
        dash = d["dash"]
        videos = dash.get("video", [])
        audios = dash.get("audio", [])
        # 选最高画质的视频
        best_video = max(videos, key=lambda v: v.get("height", 0) * v.get("width", 0)) if videos else None
        best_audio = audios[0] if audios else None
        v_url = best_video.get("baseUrl") or best_video.get("base_url") if best_video else None
        a_url = best_audio.get("baseUrl") or best_audio.get("base_url") if best_audio else None
        return v_url, a_url
    elif "durl" in d:
        durls = d["durl"]
        return durls[0]["url"] if durls else None, None
    return None, None


def _bilibili_extract_ids(url: str) -> tuple[str | None, str | None, str | None]:
    """从 B站 URL 或页面提取 (bvid, cid, title)"""
    from curl_cffi import requests as cffi_requests

    bvid_match = re.search(r"(BV[a-zA-Z0-9]+)", url)
    bvid = bvid_match.group(1) if bvid_match else None

    resp = cffi_requests.get(url, impersonate="chrome", timeout=30)
    if resp.status_code != 200:
        return bvid, None, None

    cid_match = re.search(r'"cid":(\d+)', resp.text)
    cid = cid_match.group(1) if cid_match else None

    title_match = re.search(r"<title[^>]*>(.*?)</title>", resp.text, re.DOTALL)
    title = title_match.group(1).strip() if title_match else None
    if title:
        title = re.sub(r"_哔哩哔哩_bilibili$", "", title).strip()

    return bvid, cid, title


def _bilibili_download(url: str, run_dir: Path, title: str | None = None,
                       stream_urls: tuple[str | None, str | None] | None = None) -> Path:
    """B站视频下载（curl_cffi 绕过 412），支持 DASH 和直链。

    stream_urls: 已获取的 (video_url, audio_url)，避免重复请求 playurl。
    """
    from curl_cffi import requests as cffi_requests

    bvid, cid, extracted_title = _bilibili_extract_ids(url)
    if not bvid or not cid:
        raise RuntimeError("无法从 B站 URL 提取 bvid/cid")

    # 优先使用传入的标题，否则使用提取的标题
    title = title or extracted_title or "video"
    safe_title = _slugify(title)

    print(f"  📺 B站 BVID={bvid} CID={cid} 标题={title}")
    if stream_urls:
        v_url, a_url = stream_urls
    else:
        v_url, a_url = _bilibili_get_stream_urls(bvid, cid)
    if not v_url:
        raise RuntimeError("B站 playurl API 未返回视频流")

    headers = {"Referer": "https://www.bilibili.com", "User-Agent": "Mozilla/5.0"}

    if a_url:
        # DASH：分别下载视频和音频，合并
        v_tmp = run_dir / f"_{safe_title}_video_only.m4s"
        a_tmp = run_dir / f"_{safe_title}_audio_only.m4s"
        out_path = run_dir / f"{safe_title}.mp4"

        print(f"  ⬇️  下载视频流...")
        vr = cffi_requests.get(v_url, headers=headers, impersonate="chrome", timeout=120, stream=True)
        with open(v_tmp, "wb") as f:
            for chunk in vr.iter_content(chunk_size=1024 * 256):
                f.write(chunk)

        print(f"  ⬇️  下载音频流...")
        ar = cffi_requests.get(a_url, headers=headers, impersonate="chrome", timeout=120, stream=True)
        with open(a_tmp, "wb") as f:
            for chunk in ar.iter_content(chunk_size=1024 * 256):
                f.write(chunk)

        print(f"  🔀 合并音视频...")
        run_cmd(["ffmpeg", "-y", "-i", str(v_tmp), "-i", str(a_tmp),
                 "-c:v", "copy", "-c:a", "copy", "-movflags", "+faststart",
                 str(out_path)], timeout=120)
        v_tmp.unlink(missing_ok=True)
        a_tmp.unlink(missing_ok=True)
        return out_path
    else:
        # 直链
        out_path = run_dir / f"{safe_title}.mp4"
        print(f"  ⬇️  下载视频...")
        r = cffi_requests.get(v_url, headers=headers, impersonate="chrome", timeout=120, stream=True)
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                f.write(chunk)
        return out_path


def download_video(url: str, run_dir: Path, title: str | None = None, proxy: str | None = None,
                    cookies_from_browser: str | None = None) -> Path:
    """下载视频到 run 目录

    cookies_from_browser: B站 412 时从浏览器读取 cookies（chrome/firefox/safari/edge）
    """
    import yt_dlp

    # B站优先使用 curl_cffi 绕过 412
    if _is_bilibili_url(url):
        try:
            from curl_cffi import requests as _  # noqa: F401
            print("  ⬇️  下载视频（curl_cffi 模式，策略1：buvid cookies）...")
            bvid, cid, _ = _bilibili_extract_ids(url)
            v_url, a_url, is_v_voucher = _bilibili_get_stream_urls_with_cookies(bvid, cid)
            if is_v_voucher:
                print("  ⚠️  B站 v_voucher 风控，未登录态无法获取视频流")
                if cookies_from_browser:
                    print(f"  💡  策略2：使用 {cookies_from_browser} 浏览器 cookies 重试...")
                    v_url2, a_url2, is_v2 = _bilibili_get_stream_urls_with_cookies(bvid, cid)
                    if not is_v2 and v_url2:
                        return _bilibili_download(url, run_dir, title, stream_urls=(v_url2, a_url2))
                print("  ❌  该视频触发B站风控，需登录态。请用 --cookies-from-browser chrome 重试，或在浏览器登录B站。")
                raise RuntimeError("BILI_V_VOUCHER_NEED_LOGIN")
            if v_url:
                # 复用已获取的流 URL，不再重复请求 playurl
                return _bilibili_download(url, run_dir, title, stream_urls=(v_url, a_url))
            print("  ⚠️  curl_cffi 未获取视频流，回退到 yt-dlp...")
        except RuntimeError as e:
            if "BILI_V_VOUCHER_NEED_LOGIN" in str(e):
                raise
        except Exception as e:
            print(f"  ⚠️  curl_cffi 下载失败（{e}），回退到 yt-dlp...")

    print(f"  ⬇️  下载视频...")
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "outtmpl": str(run_dir / "video.%(ext)s"),
        "merge_output_format": "mp4",
    }
    if proxy:
        ydl_opts["proxy"] = proxy
    if cookies_from_browser:
        ydl_opts["cookiesfrombrowser"] = (cookies_from_browser,)

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    for ext in ["mp4", "webm", "mkv", "mov"]:
        candidate = run_dir / f"video.{ext}"
        if candidate.exists():
            if ext != "mp4":
                mp4_path = run_dir / "video.mp4"
                candidate.rename(mp4_path)
                return mp4_path
            return candidate

    raise RuntimeError("视频下载后找不到文件")


# ── 音频提取 ────────────────────────────────────────────────


def extract_audio(video_path: Path, run_dir: Path) -> Path:
    """从视频提取音频"""
    audio_path = run_dir / "audio.wav"
    if audio_path.exists():
        print(f"  ✅ 音频已存在：{audio_path.name}")
        return audio_path

    print(f"  🎵 提取音频...")
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vn", "-acodec", "pcm_s16le",
        "-ar", "16000", "-ac", "1",
        str(audio_path)
    ]
    run_cmd(cmd, timeout=300)
    print(f"  ✅ 音频提取完成：{audio_path.name}")
    return audio_path


# ── ASR 转录 ────────────────────────────────────────────────


def transcribe_audio(audio_path: Path, run_dir: Path, model: str, language: str = "zh") -> None:
    """使用 mlx-whisper 转录音频"""
    import mlx_whisper

    transcript_json_path = run_dir / "transcript.json"
    transcript_txt_path = run_dir / "transcript.txt"

    if transcript_json_path.exists() and transcript_txt_path.exists():
        print(f"  ✅ 转录已存在，跳过")
        return

    print(f"  🎙️  ASR 转录...")
    result = mlx_whisper.transcribe(str(audio_path), path_or_hf_repo=model, language=language)

    segments = []
    for seg in result.get("segments", []):
        segments.append({
            "start": seg.get("start"),
            "end": seg.get("end"),
            "text": seg.get("text", "").strip(),
        })

    transcript_json_path.write_text(json.dumps(segments, ensure_ascii=False, indent=2), encoding="utf-8")

    full_text = "\n".join(seg["text"] for seg in segments)
    transcript_txt_path.write_text(full_text, encoding="utf-8")

    print(f"  ✅ ASR 完成：{len(segments)} 段")


# ── 字幕保存为 transcript ─────────────────────────────────


def save_subtitle_as_transcript(subtitle_text: str, transcript_json_path: Path, transcript_txt_path: Path, language: str, run_dir: Path | None = None) -> None:
    """将字幕文本保存为 transcript 格式"""
    lines = [line.strip() for line in subtitle_text.splitlines() if line.strip()]

    segments = []
    if run_dir:
        seg_cache = run_dir / "_subtitle_segments.json"
        if seg_cache.exists():
            try:
                segments = json.loads(seg_cache.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass

    if not segments:
        segments = [{"start": None, "end": None, "text": line} for line in lines]

    transcript_json_path.write_text(json.dumps(segments, ensure_ascii=False, indent=2), encoding="utf-8")
    transcript_txt_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"  ✅ 字幕转录完成：{len(lines)} 行")


# ── 清理 ────────────────────────────────────────────────────


def cleanup(run_dir: Path, mode: str) -> None:
    """清理中间文件"""
    if mode == "all":
        for f in run_dir.glob("audio.wav"):
            f.unlink(missing_ok=True)
            print(f"  🗑️  已删除：{f.name}")
    elif mode == "transcript-only":
        for f in run_dir.glob("video.mp4"):
            f.unlink(missing_ok=True)
            print(f"  🗑️  已删除：{f.name}")
        for f in run_dir.glob("audio.wav"):
            f.unlink(missing_ok=True)
            print(f"  🗑️  已删除：{f.name}")


# ── 主流程 ────────────────────────────────────────────────────


def cmd_process(args: argparse.Namespace) -> None:
    """主流程：URL/本地路径 → 字幕优先 → ASR fallback → 输出"""
    user_input = args.input
    is_url = _is_url(user_input)

    check_dependencies(
        fatal=True,
        check_asr=not is_url or args.no_subtitle,
        check_download=is_url,
    )

    base_dir = Path(args.output_dir)
    base_dir.mkdir(parents=True, exist_ok=True)

    # 先获取标题（URL输入时）
    title = None
    if is_url:
        try:
            info = fetch_video_info(user_input)
            title = info.get("title")
        except Exception:
            pass

    if not title:
        title = Path(user_input).stem if not is_url else "video"

    # 构建 run 目录名称：视频标题_时间戳
    run_dir_name = _build_run_dir_name(title, user_input)
    run_dir = base_dir / run_dir_name
    run_dir.mkdir(parents=True, exist_ok=True)

    # 记录时间戳用于后续文件名
    ts = _timestamp()
    transcript_json_path = run_dir / "transcript.json"
    transcript_txt_path = run_dir / "transcript.txt"

    if is_url:
        print(f"🔗 {user_input}")
        print(f"📝 视频标题：{title}")

        print("\n🔤 尝试获取平台字幕...")
        has_subtitle, subtitle_text, fetched_title = fetch_subtitles(user_input, run_dir, args.language)

        if fetched_title:
            title = fetched_title

        if has_subtitle and subtitle_text:
            save_subtitle_as_transcript(subtitle_text, transcript_json_path, transcript_txt_path, args.language, run_dir)
        else:
            title = title or "video"
            video_path = download_video(user_input, run_dir, title, args.proxy,
                                        cookies_from_browser=getattr(args, 'cookies_from_browser', None))
            audio_path = extract_audio(video_path, run_dir)
            transcribe_audio(audio_path, run_dir, args.asr_model, args.language)

    else:
        video_path = Path(user_input).expanduser().resolve()
        if not video_path.exists():
            print(f"❌ 视频文件不存在：{video_path}", file=sys.stderr)
            sys.exit(2)

        print(f"📁 {video_path.name}")
        print(f"📝 视频标题：{title}")

        run_video = run_dir / video_path.name
        if not run_video.exists():
            try:
                os.symlink(str(video_path), str(run_video))
                print(f"  🔗 已链接视频：{run_video.name}")
            except OSError:
                import shutil
                shutil.copy2(str(video_path), str(run_video))
                print(f"  📋 已复制视频：{run_video.name}")

        audio_path = extract_audio(run_video, run_dir)
        transcribe_audio(audio_path, run_dir, args.asr_model, args.language)

    # 生成最终摘要文件：视频标题_总结_时间戳.md
    summary_path = run_dir / _build_summary_filename(title, ts)
    if not summary_path.exists():
        summary_path.write_text(f"# {title}\n\n", encoding="utf-8")
        print(f"  📝 创建摘要文件：{summary_path.name}")

    # 清理
    if args.cleanup:
        cleanup(run_dir, args.cleanup)

    # 输出结果
    result = {
        "run_dir": str(run_dir.resolve()),
        "title": title,
        "source": "subtitle" if is_url and has_subtitle else "asr",
        "transcript_json": str(transcript_json_path.resolve()) if transcript_json_path.exists() else None,
        "transcript_txt": str(transcript_txt_path.resolve()) if transcript_txt_path.exists() else None,
        "summary_md": str(summary_path.resolve()) if summary_path.exists() else None,
    }
    print(f"\n✅ 完成！（来源：{'字幕' if result['source'] == 'subtitle' else 'ASR'}）")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _build_arg_parser():
    parser = argparse.ArgumentParser(
        description="video-summary：视频 URL 或本地文件 → 下载 + 字幕/ASR → 摘要"
    )
    parser.add_argument("input", nargs="?", help="视频 URL 或本地文件路径；也可传 doctor 诊断")
    parser.add_argument("--output-dir", default="./runs", help="产物目录（默认 ./runs）")
    parser.add_argument("--asr-model", default="mlx-community/whisper-large-v3-turbo", help="mlx-whisper 模型")
    parser.add_argument("--language", default="zh", help="语言（默认 zh）")
    parser.add_argument("--proxy", default=None, help="代理地址")
    parser.add_argument("--cleanup", default=None, choices=["all", "transcript-only"], help="清理模式")
    parser.add_argument("--no-subtitle", action="store_true", help="跳过字幕，强制使用 ASR")
    parser.add_argument("--cookies-from-browser", default=None,
                        choices=["chrome", "firefox", "safari", "edge"],
                        help="从浏览器读取 cookies（B站 412 反爬时使用）")
    return parser


def main():
    parser = _build_arg_parser()
    args = parser.parse_args()

    if args.input == "doctor":
        cmd_doctor()
        return

    if not args.input:
        parser.print_help()
        sys.exit(1)

    cmd_process(args)


if __name__ == "__main__":
    main()
