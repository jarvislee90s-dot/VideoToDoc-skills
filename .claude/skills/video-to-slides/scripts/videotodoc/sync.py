from __future__ import annotations

from pathlib import Path

from .config import Settings
from .models import SlideSet, Transcript


def estimate_sync_offset_ms(audio_path: Path, slides: SlideSet, transcript: Transcript, settings: Settings) -> int:
    """返回用户指定的同步偏移，默认 0。

    视频和音频在同一时间轴上：视频第 N 秒的画面对应音频第 N 秒的声音。
    ASR 时间戳（mlx-whisper / faster-whisper）也是相对于音频的绝对时间，
    因此截图和转录天然对齐，不需要自动偏移。

    如果用户发现图文有系统性时间偏移（比如 ASR 比画面快/慢了几秒），
    可以通过 --sync-offset-ms 手动修正。
    """
    if settings.sync_offset_ms is not None:
        return int(settings.sync_offset_ms)
    return 0
