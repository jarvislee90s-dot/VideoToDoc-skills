from __future__ import annotations

import re
from pathlib import Path

from .config import Settings
from .models import SlideSet, Transcript
from .utils import run_command


def estimate_sync_offset_ms(audio_path: Path, slides: SlideSet, transcript: Transcript, settings: Settings) -> int:
    if settings.sync_offset_ms is not None:
        return int(settings.sync_offset_ms)

    audio_onset = detect_first_audio_onset_ms(audio_path)
    first_slide = slides.slides[0].start_ms if slides.slides else 0
    first_transcript = transcript.segments[0].start_ms if transcript.segments else audio_onset
    return int((audio_onset - first_transcript) + first_slide * 0)


def detect_first_audio_onset_ms(audio_path: Path) -> int:
    result = run_command(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(audio_path),
            "-af",
            "silencedetect=noise=-35dB:d=0.2",
            "-f",
            "null",
            "-",
        ]
    )
    text = result.stderr + "\n" + result.stdout
    silence_end = re.search(r"silence_end: ([0-9.]+)", text)
    if silence_end:
        return int(float(silence_end.group(1)) * 1000)
    return 0
