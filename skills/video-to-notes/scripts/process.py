#!/usr/bin/env python3
"""video-to-notes: 视频链接 → 字幕/转录 → Markdown

流程：URL → 字幕优先 → 无字幕时(下载音频 → ASR) → 输出 transcript.txt

借鉴：
- tscribe 的 CLI 设计：一条命令跑完，doctor 诊断
- AI-Video-Transcriber 的字幕优先策略：优先平台原生字幕，fallback 到 ASR
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

# ── 站点代理映射 ──────────────────────────────────────────────

SITE_PROXY_MAP: dict[str, str] = {}

_env_proxy = os.environ.get("VIDEO_TO_NOTES_PROXY_MAP", "")
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


def _is_bilibili_url(url: str) -> bool:
    return "bilibili.com" in url or "b23.tv" in url


# ── 依赖检查 & 诊断 ─────────────────────────────────────────


def check_dependencies(fatal: bool = True, check_asr: bool = False) -> list[tuple[str, str, bool]]:
    """检查依赖，返回 [(名称, 安装命令, 是否可用)] 列表
    
    Args:
        fatal: 缺少必需依赖时是否退出
        check_asr: 是否检查 ASR 依赖（mlx-whisper）
    """
    results = []

    # yt-dlp（必需）
    try:
        import yt_dlp  # noqa: F401
        results.append(("yt-dlp", "pip install yt-dlp pycryptodomex", True))
    except ModuleNotFoundError:
        results.append(("yt-dlp", "pip install yt-dlp pycryptodomex", False))

    # ffmpeg（字幕获取时可选，ASR 时必需）
    try:
        run_cmd(["ffmpeg", "-version"])
        results.append(("ffmpeg", "brew install ffmpeg (macOS)", True))
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        results.append(("ffmpeg", "brew install ffmpeg (macOS)", False))

    # mlx_whisper（仅在需要 ASR 时检查）
    if check_asr:
        try:
            import mlx_whisper  # noqa: F401
            results.append(("mlx-whisper", "pip install mlx-whisper", True))
        except ModuleNotFoundError:
            results.append(("mlx-whisper", "pip install mlx-whisper", False))

    # curl_cffi (可选，用于 B站 TLS 指纹绕过)
    try:
        from curl_cffi import requests as _  # noqa: F401
        results.append(("curl_cffi", "pip install curl_cffi (可选)", True))
    except ModuleNotFoundError:
        results.append(("curl_cffi", "pip install curl_cffi (可选，用于B站)", False))

    # 必需依赖：yt-dlp
    if fatal and not results[0][2]:
        print("❌ 缺少必需依赖：\n")
        for name, cmd, ok in results:
            if not ok and name in ["yt-dlp"]:
                print(f"  {name}: {cmd}")
        sys.exit(1)

    return results


def cmd_doctor() -> None:
    """诊断依赖和配置状态"""
    print("🔍 video-to-notes 诊断\n")
    results = check_dependencies(fatal=False, check_asr=True)
    for name, cmd, ok in results:
        status = "✅" if ok else "❌"
        print(f"  {status} {name}")
        if not ok:
            print(f"     安装：{cmd}")
    print()


# ── 步骤 ①：探测视频信息 ───────────────────────────────────────


def probe_video(url: str) -> dict:
    """用 yt-dlp 快速探测视频信息（不下载）"""
    try:
        import yt_dlp
    except ModuleNotFoundError:
        print("❌ 未安装 yt-dlp")
        sys.exit(1)

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "cookies_from_browser": ("safari",) if _is_bilibili_url(url) else None,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    return {
        "title": info.get("title", "video"),
        "duration": info.get("duration", 0),
        "uploader": info.get("uploader", ""),
        "has_subtitles": bool(info.get("subtitles")),
        "has_auto_captions": bool(info.get("automatic_captions")),
    }


# ── 步骤 ②：字幕优先下载 ───────────────────────────────────────


def fetch_subtitles(url: str, run_dir: Path, language: str = "zh") -> tuple[bool, str | None, str]:
    """优先下载平台原生字幕（比 ASR 快很多）

    借鉴 AI-Video-Transcriber 的字幕优先策略：
    1. 检查 info 中的 subtitles / automatic_captions
    2. 优先人工字幕，其次自动字幕
    3. 按语言优先级选择：zh-Hans > zh > en > 其他
    4. 下载字幕文件并解析为纯文本

    Returns: (是否成功, 字幕纯文本, 视频标题)
    """
    try:
        import yt_dlp
    except ModuleNotFoundError:
        return False, None, ""

    try:
        # 1. 探测视频信息和字幕可用性
        check_opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "cookies_from_browser": ("safari",) if _is_bilibili_url(url) else None,
        }
        with yt_dlp.YoutubeDL(check_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        title = info.get("title", "video")
        manual_subs: dict = info.get("subtitles") or {}
        auto_caps: dict = info.get("automatic_captions") or {}

        # 过滤非语音轨道
        manual_langs = [k for k in manual_subs if not k.startswith("live_chat")]
        auto_langs = [k for k in auto_caps if not k.startswith("live_chat")]

        if not manual_langs and not auto_langs:
            print("  ℹ️  视频无可用字幕，将使用 ASR")
            return False, None, title

        # 2. 优先人工字幕
        prefer_manual = bool(manual_langs)
        candidate_langs = manual_langs if prefer_manual else auto_langs

        # 3. 按优先级选语言
        _priority = ["zh-Hans", "zh-Hant", "zh", "en", "ja", "ko"]
        prefer_lang = next(
            (lang for lang in _priority if lang in candidate_langs),
            candidate_langs[0],
        )
        sub_type = "手动" if prefer_manual else "自动"
        print(f"  🔤 发现{sub_type}字幕，语言：{prefer_lang}（候选 {len(candidate_langs)} 种）")

        # 4. 仅下载字幕文件
        sub_dir = run_dir / ".subs"
        sub_dir.mkdir(exist_ok=True)
        dl_opts = {
            "writesubtitles": prefer_manual,
            "writeautomaticsub": not prefer_manual,
            "subtitlesformat": "srt/best",
            "subtitleslangs": [prefer_lang],
            "skip_download": True,
            "outtmpl": str(sub_dir / "sub.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "cookies_from_browser": ("safari",) if _is_bilibili_url(url) else None,
        }
        with yt_dlp.YoutubeDL(dl_opts) as ydl:
            ydl.download([url])

        # 5. 查找并解析字幕文件
        for ext in ["srt", "vtt", "ass", "lrc"]:
            sub_file = sub_dir / f"sub.{ext}"
            if sub_file.exists():
                text = _parse_subtitle_file(sub_file)
                if text:
                    print(f"  ✅ 字幕提取完成：{len(text)} 字")
                    # 清理临时字幕目录
                    shutil.rmtree(sub_dir, ignore_errors=True)
                    return True, text, title

        print("  ⚠️  字幕文件解析失败，将使用 ASR")
        shutil.rmtree(sub_dir, ignore_errors=True)
        return False, None, title

    except Exception as e:
        print(f"  ⚠️  字幕下载失败（{e}），将使用 ASR")
        return False, None, ""


def _parse_subtitle_file(path: Path) -> str | None:
    """解析 SRT/VTT 字幕文件，提取纯文本"""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

    lines = []
    for line in content.splitlines():
        line = line.strip()
        # 跳过序号、时间轴、空行、标签
        if not line:
            continue
        if re.match(r'^\d+$', line):
            continue
        if re.match(r'^\d{2}:\d{2}', line) or '-->' in line:
            continue
        if line.startswith('WEBVTT') or line.startswith('NOTE'):
            continue
        # 清理 HTML 标签
        line = re.sub(r'<[^>]+>', '', line)
        if line:
            lines.append(line)

    return "\n".join(lines) if lines else None


# ── 步骤 ③：下载视频（仅音频） ────────────────────────────────


def download_audio(url: str, run_dir: Path, proxy: str | None = None) -> Path:
    """用 yt-dlp 下载最佳音频流（参考 tscribe：只下音频，不下视频）"""
    effective_proxy = _get_proxy_for_url(url, proxy)

    try:
        import yt_dlp
    except ModuleNotFoundError:
        print("❌ 未安装 yt-dlp")
        sys.exit(1)

    outtmpl = str(run_dir / "audio.%(ext)s")

    last_log = [0.0]
    def progress_hook(d):
        if d["status"] == "downloading":
            now = time.time()
            if now - last_log[0] < 10:
                return
            last_log[0] = now
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes", 0)
            speed = d.get("speed", 0)
            eta = d.get("eta")
            pct = f"{downloaded / total * 100:.1f}%" if total else "??%"
            speed_str = f"{_format_bytes(speed)}/s" if speed else "??"
            eta_str = _format_seconds(eta) if eta is not None else "??:??"
            print(f"  {pct}  速度: {speed_str}  剩余: {eta_str}")
        elif d["status"] == "finished":
            print(f"  ✅ 音频下载完成")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "extract_audio": True,
        "audio_format": "wav",
        "audioquality": "0",
        "postprocessor_args": ["-ac", "1", "-ar", "16000"],
        "prefer_ffmpeg": True,
        "proxy": effective_proxy or "",
        "quiet": True,
        "no_warnings": True,
        "no_progress": True,
        "noplaylist": True,
        "progress_hooks": [progress_hook],
        "cookies_from_browser": ("safari",) if _is_bilibili_url(url) else None,
    }

    print(f"\n📥 下载音频...")
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        title = info.get("title", "video")

    # 找到音频文件
    audio_path = run_dir / "audio.wav"
    if not audio_path.exists():
        for ext in ["m4a", "mp3", "ogg", "wav"]:
            candidate = run_dir / f"audio.{ext}"
            if candidate.exists():
                audio_path = candidate
                break

    if not audio_path.exists():
        print("❌ 下载完成但找不到音频文件")
        sys.exit(1)

    return audio_path


# ── 步骤 ④：ASR 转录 ─────────────────────────────────────────


def transcribe_audio(
    audio_path: Path,
    transcript_json_path: Path,
    transcript_txt_path: Path,
    asr_model: str,
    language: str,
) -> None:
    """用 mlx-whisper 转录"""
    if transcript_json_path.exists() and transcript_txt_path.exists():
        json_size = transcript_json_path.stat().st_size
        txt_size = transcript_txt_path.stat().st_size
        if json_size > 0 and txt_size > 0:
            print("  ⏭️  转录结果已存在，跳过 ASR")
            return
        transcript_json_path.unlink(missing_ok=True)
        transcript_txt_path.unlink(missing_ok=True)

    print(f"\n🎙️ 正在转录（模型：{asr_model}）...")

    try:
        import mlx_whisper
    except ModuleNotFoundError:
        print("❌ 未安装 mlx-whisper，请执行：pip install mlx-whisper")
        transcript_json_path.unlink(missing_ok=True)
        transcript_txt_path.unlink(missing_ok=True)
        sys.exit(1)

    kwargs = {
        "path_or_hf_repo": asr_model,
        "language": language,
        "initial_prompt": "以下是普通话的句子。" if language == "zh" else "",
    }
    try:
        result = mlx_whisper.transcribe(str(audio_path), **kwargs)
    except TypeError:
        kwargs.pop("initial_prompt", None)
        result = mlx_whisper.transcribe(str(audio_path), **kwargs)
    except Exception as e:
        transcript_json_path.unlink(missing_ok=True)
        transcript_txt_path.unlink(missing_ok=True)
        print(f"❌ ASR 转录失败：{e}")
        sys.exit(1)

    segments = []
    text_lines = []
    for seg in result.get("segments", []):
        start_ms = int(round(float(seg.get("start", 0)) * 1000))
        end_ms = int(round(float(seg.get("end", 0)) * 1000))
        text = str(seg.get("text", "")).strip()
        if not text:
            continue
        segments.append({"start_ms": start_ms, "end_ms": end_ms, "text": text})
        text_lines.append(text)

    transcript_data = {
        "backend": "mlx-whisper",
        "model": asr_model,
        "language": result.get("language", language),
        "segments": segments,
    }
    transcript_json_path.write_text(json.dumps(transcript_data, ensure_ascii=False, indent=2), encoding="utf-8")
    transcript_txt_path.write_text("\n".join(text_lines), encoding="utf-8")

    duration_sec = segments[-1]["end_ms"] / 1000 if segments else 0
    print(f"  ✅ 转录完成：{len(segments)} 段，时长 {_format_seconds(duration_sec)}")


# ── 步骤 ⑤：保存字幕来源的转录 ────────────────────────────────


def save_subtitle_as_transcript(
    subtitle_text: str,
    transcript_json_path: Path,
    transcript_txt_path: Path,
    language: str,
) -> None:
    """将字幕文本保存为标准转录格式"""
    lines = [line.strip() for line in subtitle_text.splitlines() if line.strip()]

    segments = []
    for i, line in enumerate(lines):
        segments.append({"start_ms": i * 5000, "end_ms": (i + 1) * 5000, "text": line})

    transcript_data = {
        "backend": "subtitle",
        "model": "platform-subtitle",
        "language": language,
        "segments": segments,
    }
    transcript_json_path.write_text(json.dumps(transcript_data, ensure_ascii=False, indent=2), encoding="utf-8")
    transcript_txt_path.write_text(subtitle_text, encoding="utf-8")
    print(f"  ✅ 字幕转录保存完成：{len(lines)} 行")


# ── 清理 ──────────────────────────────────────────────────────


def cleanup(run_dir: Path, mode: str) -> set[str]:
    cleaned = set()
    if mode == "all":
        for name in ["audio.wav", "audio.m4a"]:
            f = run_dir / name
            if f.exists():
                f.unlink()
                cleaned.add(name)
                print(f"  🗑️  已清理：{name}")
    elif mode == "transcript-only":
        for name in ["audio.wav", "audio.m4a", "transcript.json", "transcript.txt"]:
            f = run_dir / name
            if f.exists():
                f.unlink()
                cleaned.add(name)
                print(f"  🗑️  已清理：{name}")
    return cleaned


# ── 主流程 ────────────────────────────────────────────────────


def cmd_process(args: argparse.Namespace) -> None:
    """主流程：URL → 字幕优先 → ASR fallback → 输出"""
    check_dependencies(fatal=True, check_asr=args.no_subtitle)  # 强制 ASR 时需要检查 ASR 依赖

    url = args.url
    base_dir = Path(args.output_dir)
    base_dir.mkdir(parents=True, exist_ok=True)

    print(f"🔗 {url}")
    run_dir_name = f"notes_{_short_hash(url)}"
    run_dir = base_dir / run_dir_name
    run_dir.mkdir(parents=True, exist_ok=True)

    transcript_json_path = run_dir / "transcript.json"
    transcript_txt_path = run_dir / "transcript.txt"

    # ① 字幕优先策略
    print("\n🔤 尝试获取平台字幕...")
    has_subtitle, subtitle_text, title = fetch_subtitles(url, run_dir, args.language)

    if has_subtitle and subtitle_text:
        # 字幕成功，直接保存为转录
        save_subtitle_as_transcript(subtitle_text, transcript_json_path, transcript_txt_path, args.language)
    else:
        # ② 无字幕，下载音频 + ASR
        title = title or "video"
        audio_path = download_audio(url, run_dir, args.proxy)
        transcribe_audio(audio_path, transcript_json_path, transcript_txt_path, args.asr_model, args.language)

    # ③ 用标题重命名目录
    new_dir_name = f"{_slugify(title)}_{_short_hash(url)}"
    new_dir = base_dir / new_dir_name
    if run_dir != new_dir:
        try:
            if not new_dir.exists():
                run_dir.rename(new_dir)
                run_dir = new_dir
        except OSError:
            print(f"  ⚠️  目录重命名失败，继续使用：{run_dir.name}")

    # ④ 清理
    cleaned_files: set[str] = set()
    if args.cleanup:
        cleaned_files = cleanup(run_dir, args.cleanup)

    # ⑤ 输出结果
    result = {
        "run_dir": str(run_dir.resolve()),
        "title": title,
        "source": "subtitle" if has_subtitle else "asr",
        "transcript_json": None if "transcript.json" in cleaned_files else (str(transcript_json_path.resolve()) if transcript_json_path.exists() else None),
        "transcript_txt": None if "transcript.txt" in cleaned_files else (str(transcript_txt_path.resolve()) if transcript_txt_path.exists() else None),
    }
    print(f"\n✅ 完成！（来源：{'字幕' if has_subtitle else 'ASR'}）")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(
        description="video-to-notes：视频链接 → 字幕/转录 → Markdown"
    )
    parser.add_argument("url", nargs="?", help="视频网页链接或 doctor 命令")
    parser.add_argument("--output-dir", default="./runs", help="产物目录（默认 ./runs）")
    parser.add_argument("--asr-model", default="mlx-community/whisper-large-v3-turbo", help="mlx-whisper 模型")
    parser.add_argument("--language", default="zh", help="语言（默认 zh）")
    parser.add_argument("--proxy", default=None, help="代理地址")
    parser.add_argument("--cleanup", default=None, choices=["all", "transcript-only"], help="清理模式")
    parser.add_argument("--no-subtitle", action="store_true", help="跳过字幕，强制使用 ASR")

    args = parser.parse_args()

    if args.url == "doctor":
        cmd_doctor()
        return

    if not args.url:
        parser.print_help()
        sys.exit(1)

    cmd_process(args)


if __name__ == "__main__":
    main()
