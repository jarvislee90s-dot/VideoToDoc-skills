from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from .config import Settings
from .utils import VideoToDocError, run_command


def probe_duration_ms(video_path: Path) -> int:
    """读取视频时长（毫秒）。

    优先使用 ffprobe（macOS 通常随 ffmpeg 提供）；ffprobe 不可用时
    回退到 `ffmpeg -i` 解析输出（Windows 上仅安装 ffmpeg.exe 即可）。
    """
    if shutil.which("ffprobe"):
        result = run_command(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            timeout=30,
        )
        try:
            return int(float(result.stdout.strip()) * 1000)
        except ValueError:
            pass

    # fallback：ffmpeg -i 的 stderr 含 `Duration: HH:MM:SS.xx`
    try:
        result = subprocess.run(
            ["ffmpeg", "-i", str(video_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError as exc:
        raise VideoToDocError(f"找不到命令：ffmpeg（需安装 ffmpeg 并在 PATH 中）") from exc
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", result.stderr)
    if m:
        hours, minutes = int(m.group(1)), int(m.group(2))
        seconds = float(m.group(3))
        return int((hours * 3600 + minutes * 60 + seconds) * 1000)
    raise VideoToDocError(f"无法读取视频时长：{video_path}")


def extract_audio(video_path: Path, output_path: Path, settings: Settings, force: bool = False) -> Path:
    if output_path.exists() and not force:
        return output_path

    output_path.parent.mkdir(parents=True, exist_ok=True)
    backend = settings.asr_backend.lower()
    profile = settings.audio_profile
    keep_original = profile == "source" or (profile == "auto" and backend.startswith("qwen"))

    args = ["ffmpeg", "-y", "-i", str(video_path), "-vn"]
    if keep_original:
        args += ["-acodec", "pcm_s16le"]
    else:
        args += ["-ac", "1", "-ar", "16000", "-acodec", "pcm_s16le"]
    args.append(str(output_path))
    run_command(args, timeout=300)
    return output_path
