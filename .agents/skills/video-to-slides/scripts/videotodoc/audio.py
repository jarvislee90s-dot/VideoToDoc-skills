from __future__ import annotations

from pathlib import Path

from .config import Settings
from .utils import VideoToDocError, run_command


def probe_duration_ms(video_path: Path) -> int:
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
    except ValueError as exc:
        raise VideoToDocError(f"无法读取视频时长：{video_path}") from exc


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
