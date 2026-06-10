from __future__ import annotations

import re
from pathlib import Path

from .config import Settings
from .models import Transcript, TranscriptSegment, to_plain_dict
from .io import read_json, write_json
from .utils import VideoToDocError


def transcribe_audio(audio_path: Path, output_path: Path, settings: Settings, force: bool = False) -> Transcript:
    """将音频转为统一 transcript JSON。

    第一优先级是 Apple Silicon 友好的 `mlx-whisper`。`mock` 只用于
    验证非 ASR 流水线，质量报告会把它标为非真实转录。
    """

    if output_path.exists() and not force:
        return transcript_from_dict(read_json(output_path))

    backend = settings.asr_backend.lower()
    if backend == "mock":
        transcript = _mock_transcript(settings)
    elif backend in {"mlx-whisper", "mlx_whisper", "mlx"}:
        transcript = _mlx_whisper(audio_path, settings)
    elif backend == "faster-whisper":
        transcript = _faster_whisper(audio_path, settings)
    elif backend in {"qwen", "qwen3-asr", "qwen3-asr-flash"}:
        raise VideoToDocError("Qwen3-ASR 后端接口已预留，但第一版默认不启用商业 API。请使用 --asr faster-whisper 或 --asr mock。")
    elif backend in {"funasr", "sensevoice"}:
        raise VideoToDocError(f"{backend} 后端已预留为插件式扩展，当前版本尚未实现。")
    else:
        raise VideoToDocError(f"未知 ASR 后端：{settings.asr_backend}")

    transcript.segments = normalize_segments(transcript.segments, settings)
    write_json(output_path, to_plain_dict(transcript))
    return transcript


def normalize_segments(segments: list[TranscriptSegment], settings: Settings) -> list[TranscriptSegment]:
    normalized: list[TranscriptSegment] = []
    for segment in segments:
        text = segment.text.strip()
        for source, target in settings.terms.items():
            text = re.sub(re.escape(source), target, text, flags=re.IGNORECASE)
        text = _normalize_math_symbols(text)
        if segment.confidence is not None and segment.confidence < settings.low_confidence_threshold:
            text = f"[低置信度] {text}"
        normalized.append(
            TranscriptSegment(
                start_ms=max(0, int(segment.start_ms)),
                end_ms=max(int(segment.start_ms), int(segment.end_ms)),
                text=text,
                confidence=segment.confidence,
            )
        )
    return normalized


def transcript_from_dict(data: dict) -> Transcript:
    return Transcript(
        backend=data.get("backend", ""),
        language=data.get("language", "zh"),
        prompt=data.get("prompt", ""),
        metadata=data.get("metadata", {}),
        segments=[TranscriptSegment(**item) for item in data.get("segments", [])],
    )


def _faster_whisper(audio_path: Path, settings: Settings) -> Transcript:
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ModuleNotFoundError as exc:
        raise VideoToDocError(
            "未安装 faster-whisper。可执行 `python3 -m pip install '.[asr]'`，"
            "或先用 `--asr mock` 验证非 ASR 流水线。"
        ) from exc

    model = WhisperModel(settings.asr_model, device="auto", compute_type="auto")
    segments, info = model.transcribe(
        str(audio_path),
        language=settings.language,
        initial_prompt=settings.prompt,
        vad_filter=True,
    )
    items: list[TranscriptSegment] = []
    for segment in segments:
        confidence = None
        if getattr(segment, "avg_logprob", None) is not None:
            confidence = max(0.0, min(1.0, (float(segment.avg_logprob) + 1.5) / 1.5))
        items.append(
            TranscriptSegment(
                start_ms=int(round(segment.start * 1000)),
                end_ms=int(round(segment.end * 1000)),
                text=segment.text,
                confidence=confidence,
            )
        )
    return Transcript(
        backend="faster-whisper",
        language=getattr(info, "language", settings.language),
        prompt=settings.prompt,
        segments=items,
        metadata={"model": settings.asr_model},
    )


def _mlx_whisper(audio_path: Path, settings: Settings) -> Transcript:
    try:
        import mlx_whisper  # type: ignore
    except ModuleNotFoundError as exc:
        raise VideoToDocError(
            "未安装 mlx-whisper。可执行 `python3 -m pip install -U mlx-whisper`，"
            "或先用 `--asr mock` 验证截图和文档流程。"
        ) from exc

    kwargs = {
        "path_or_hf_repo": settings.asr_model,
        "language": settings.language,
        "initial_prompt": settings.prompt,
    }
    try:
        result = mlx_whisper.transcribe(str(audio_path), **kwargs)
    except TypeError:
        # 兼容不同 mlx-whisper 版本的参数表。
        kwargs.pop("initial_prompt", None)
        result = mlx_whisper.transcribe(str(audio_path), **kwargs)

    items: list[TranscriptSegment] = []
    for segment in result.get("segments", []):
        items.append(
            TranscriptSegment(
                start_ms=int(round(float(segment.get("start", 0)) * 1000)),
                end_ms=int(round(float(segment.get("end", 0)) * 1000)),
                text=str(segment.get("text", "")).strip(),
                confidence=None,
            )
        )
    return Transcript(
        backend="mlx-whisper",
        language=result.get("language", settings.language),
        prompt=settings.prompt,
        segments=items,
        metadata={"model": settings.asr_model},
    )


def _mock_transcript(settings: Settings) -> Transcript:
    return Transcript(
        backend="mock",
        language=settings.language,
        prompt=settings.prompt,
        metadata={"warning": "mock transcript，仅用于测试流水线。"},
        segments=[
            TranscriptSegment(0, 30000, "这是第一部分的课程讲解，用于验证图文对齐流程。", 1.0),
            TranscriptSegment(30000, 90000, "这里讨论核心概念、公式和英文术语 API、Python、GitHub。", 1.0),
            TranscriptSegment(90000, 180000, "最后总结本节课的重点和后续需要复习的内容。", 1.0),
        ],
    )


def _normalize_math_symbols(text: str) -> str:
    replacements = {
        "大于等于": "≥",
        "小于等于": "≤",
        "不等于": "≠",
        "约等于": "≈",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text
