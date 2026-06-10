#!/usr/bin/env python3
"""video-to-notes 主流程脚本

输入网页视频链接，依次完成：
  ① yt-dlp 下载视频
  ② ffmpeg 提取音频
  ③ mlx-whisper 转录

输出 JSON（含产物路径），供 Agent 读取 transcript.txt 后自行总结。
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
from pathlib import Path

# ── 站点代理映射（参考 VideoDownloader） ──────────────────────

SITE_PROXY_MAP: dict[str, str] = {
    "91nt.com": "http://127.0.0.1:29290",
}


# ── 工具函数 ──────────────────────────────────────────────────


def _get_proxy_for_url(url: str, user_proxy: str | None = None) -> str | None:
    """根据 URL 获取代理：用户指定 > 站点配置 > None"""
    if user_proxy is not None:
        return user_proxy
    for domain, proxy in SITE_PROXY_MAP.items():
        if domain in url:
            return proxy
    return None


def _slugify(text: str) -> str:
    """将标题转为文件系统友好的 slug"""
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', text)
    text = re.sub(r'_+', '_', text).strip('_')
    return text[:80] or "video"


def _short_hash(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()[:12]


def _format_bytes(n: float) -> str:
    if n is None or n <= 0:
        return "??"
    for unit in ["B", "KiB", "MiB", "GiB"]:
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TiB"


def _format_seconds(s: float) -> str:
    if s is None or s < 0:
        return "??:??"
    m, sec = divmod(int(s), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


def run_cmd(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """运行外部命令，捕获输出"""
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


# ── 依赖检查 ──────────────────────────────────────────────────


def check_dependencies() -> None:
    """启动时一次性检查所有依赖，缺什么打印安装命令并退出"""
    missing = []

    # yt-dlp
    try:
        run_cmd(["yt-dlp", "--version"])
    except (FileNotFoundError, subprocess.CalledProcessError):
        missing.append(("yt-dlp", "pip install yt-dlp pycryptodomex"))

    # ffmpeg
    try:
        run_cmd(["ffmpeg", "-version"])
    except (FileNotFoundError, subprocess.CalledProcessError):
        missing.append(("ffmpeg", "brew install ffmpeg  (macOS)"))

    # mlx_whisper
    try:
        import mlx_whisper  # noqa: F401
    except ModuleNotFoundError:
        missing.append(("mlx-whisper", "pip install mlx-whisper"))

    if missing:
        print("❌ 缺少以下依赖，请安装后重试：\n")
        for name, install_cmd in missing:
            print(f"  {name}: {install_cmd}")
        print()
        sys.exit(1)


# ── 步骤 ①：下载视频 ─────────────────────────────────────────


def download_video(
    url: str,
    output_dir: Path,
    resolution: str = "best",
    proxy: str | None = None,
) -> tuple[Path, str]:
    """用 yt-dlp 下载视频，返回 (视频路径, 视频标题)"""
    effective_proxy = _get_proxy_for_url(url, proxy)

    # 分辨率到 yt-dlp format 的映射
    fmt_map = {
        "best": "bestvideo*+bestaudio/best",
        "2160p": "bestvideo[height<=2160]+bestaudio/best[height<=2160]",
        "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]",
        "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]",
        "360p": "bestvideo[height<=360]+bestaudio/best[height<=360]",
        "audio": "bestaudio/best",
    }
    fmt = fmt_map.get(resolution, fmt_map["best"])

    outtmpl = str(output_dir / "video.%(ext)s")

    # 进度回调，每 10 秒打印一行
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
            down_str = _format_bytes(downloaded)
            total_str = _format_bytes(total) if total else "??"
            speed_str = f"{_format_bytes(speed)}/s" if speed else "??"
            eta_str = _format_seconds(eta) if eta is not None else "??:??"
            print(f"  {pct}  {down_str}/{total_str}  {speed_str}  剩余 {eta_str}")
        elif d["status"] == "finished":
            total = d.get("total_bytes")
            print(f"  ✅ 下载完成，大小 {_format_bytes(total)}")

    ydl_opts = {
        "format": fmt,
        "outtmpl": outtmpl,
        "merge_output_format": "mp4",
        "proxy": effective_proxy or "",
        "quiet": True,
        "no_warnings": True,
        "no_progress": True,
        "progress_hooks": [progress_hook],
    }

    try:
        import yt_dlp
    except ModuleNotFoundError:
        print("❌ 未安装 yt-dlp，请执行：pip install yt-dlp pycryptodomex")
        sys.exit(1)

    print(f"\n📥 正在下载视频：{url}")
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        title = info.get("title", "video")

    # 找到下载后的实际文件
    video_path = output_dir / "video.mp4"
    if not video_path.exists():
        # 可能是其他格式
        for ext in ["mkv", "webm", "mp4"]:
            candidate = output_dir / f"video.{ext}"
            if candidate.exists():
                video_path = candidate
                break

    if not video_path.exists():
        print("❌ 下载完成但找不到视频文件")
        sys.exit(1)

    return video_path, title


# ── 步骤 ②：提取音频 ─────────────────────────────────────────


def extract_audio(video_path: Path, output_path: Path) -> Path:
    """用 ffmpeg 提取 16kHz 单声道 WAV"""
    if output_path.exists():
        print("  ⏭️  音频已存在，跳过提取")
        return output_path

    print("\n🎵 提取音频...")
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vn", "-ac", "1", "-ar", "16000",
        "-acodec", "pcm_s16le",
        str(output_path),
    ]
    try:
        run_cmd(cmd)
    except subprocess.CalledProcessError as e:
        print(f"❌ ffmpeg 提取音频失败：{e.stderr}")
        sys.exit(1)

    print(f"  ✅ 音频已保存：{output_path.name}")
    return output_path


# ── 步骤 ③：ASR 转录 ─────────────────────────────────────────


def transcribe_audio(
    audio_path: Path,
    transcript_json_path: Path,
    transcript_txt_path: Path,
    asr_model: str,
    language: str,
) -> None:
    """用 mlx-whisper 转录，输出 JSON + 纯文本"""
    if transcript_json_path.exists() and transcript_txt_path.exists():
        print("  ⏭️  转录结果已存在，跳过 ASR")
        return

    print(f"\n🎙️ 正在转录（模型：{asr_model}）...")

    try:
        import mlx_whisper
    except ModuleNotFoundError:
        print("❌ 未安装 mlx-whisper，请执行：pip install mlx-whisper")
        sys.exit(1)

    kwargs = {
        "path_or_hf_repo": asr_model,
        "language": language,
        "initial_prompt": "以下是普通话的句子。" if language == "zh" else "",
    }
    try:
        result = mlx_whisper.transcribe(str(audio_path), **kwargs)
    except TypeError:
        # 兼容不同 mlx-whisper 版本
        kwargs.pop("initial_prompt", None)
        result = mlx_whisper.transcribe(str(audio_path), **kwargs)

    # 构建转录数据
    segments = []
    text_lines = []
    for seg in result.get("segments", []):
        start_ms = int(round(float(seg.get("start", 0)) * 1000))
        end_ms = int(round(float(seg.get("end", 0)) * 1000))
        text = str(seg.get("text", "")).strip()
        if not text:
            continue
        segments.append({
            "start_ms": start_ms,
            "end_ms": end_ms,
            "text": text,
        })
        text_lines.append(text)

    # 写入 JSON
    transcript_data = {
        "backend": "mlx-whisper",
        "model": asr_model,
        "language": result.get("language", language),
        "segments": segments,
    }
    transcript_json_path.write_text(
        json.dumps(transcript_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 写入纯文本
    transcript_txt_path.write_text(
        "\n".join(text_lines),
        encoding="utf-8",
    )

    duration_sec = segments[-1]["end_ms"] / 1000 if segments else 0
    print(f"  ✅ 转录完成：{len(segments)} 段，时长 {_format_seconds(duration_sec)}")


# ── 清理 ──────────────────────────────────────────────────────


def cleanup(run_dir: Path, mode: str) -> None:
    """按模式清理产物"""
    if mode == "all":
        # 删除视频和音频，保留转录和总结
        for name in ["video.mp4", "audio.wav"]:
            f = run_dir / name
            if f.exists():
                f.unlink()
                print(f"  🗑️  已清理：{name}")
    elif mode == "transcript-only":
        # 只保留 summary.md
        for name in ["video.mp4", "audio.wav", "transcript.json", "transcript.txt"]:
            f = run_dir / name
            if f.exists():
                f.unlink()
                print(f"  🗑️  已清理：{name}")


# ── 主流程 ────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="video-to-notes：网页视频 → 下载 → 音频 → 转录"
    )
    parser.add_argument("url", help="视频网页链接")
    parser.add_argument(
        "--output-dir", default="./runs",
        help="运行产物输出目录（默认 ./runs）",
    )
    parser.add_argument(
        "--resolution", default="best",
        choices=["best", "2160p", "1080p", "720p", "480p", "360p", "audio"],
        help="视频分辨率（默认 best）",
    )
    parser.add_argument(
        "--asr-model",
        default="mlx-community/whisper-large-v3-turbo",
        help="mlx-whisper 模型（默认 mlx-community/whisper-large-v3-turbo）",
    )
    parser.add_argument("--proxy", default=None, help="代理地址（如 http://127.0.0.1:29290）")
    parser.add_argument(
        "--cleanup", default=None,
        choices=["all", "transcript-only"],
        help="清理模式：all=删除视频+音频，transcript-only=只保留 summary.md",
    )
    parser.add_argument("--language", default="zh", help="ASR 语言（默认 zh）")
    args = parser.parse_args()

    # ① 依赖检查
    check_dependencies()

    # ② 创建运行目录
    base_dir = Path(args.output_dir)
    base_dir.mkdir(parents=True, exist_ok=True)

    # 先获取视频标题用于命名目录
    print(f"🔗 目标 URL：{args.url}")
    run_dir_name = f"notes_{_short_hash(args.url)}"
    run_dir = base_dir / run_dir_name
    run_dir.mkdir(parents=True, exist_ok=True)

    # ③ 下载视频
    video_path, title = download_video(
        args.url, run_dir, args.resolution, args.proxy,
    )

    # 下载后用标题重新命名目录
    new_dir_name = f"{_slugify(title)}_{_short_hash(args.url)}"
    new_dir = base_dir / new_dir_name
    if run_dir != new_dir and not new_dir.exists():
        run_dir.rename(new_dir)
        run_dir = new_dir
        video_path = run_dir / video_path.name

    # ④ 提取音频
    audio_path = run_dir / "audio.wav"
    extract_audio(video_path, audio_path)

    # ⑤ ASR 转录
    transcript_json_path = run_dir / "transcript.json"
    transcript_txt_path = run_dir / "transcript.txt"
    transcribe_audio(audio_path, transcript_json_path, transcript_txt_path, args.asr_model, args.language)

    # ⑥ 清理（如果指定）
    if args.cleanup:
        cleanup(run_dir, args.cleanup)

    # ⑦ 输出结果
    result = {
        "run_dir": str(run_dir.resolve()),
        "video": str((run_dir / "video.mp4").resolve()) if (run_dir / "video.mp4").exists() else None,
        "audio": str(audio_path.resolve()) if audio_path.exists() else None,
        "transcript_json": str(transcript_json_path.resolve()),
        "transcript_txt": str(transcript_txt_path.resolve()),
        "title": title,
    }
    print(f"\n✅ 全部完成！")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
