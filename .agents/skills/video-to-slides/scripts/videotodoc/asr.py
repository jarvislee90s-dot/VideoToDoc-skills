from __future__ import annotations

import re
from pathlib import Path

from .config import Settings
from .models import Transcript, TranscriptSegment, WordTimestamp, to_plain_dict
from .io import read_json, write_json
from .utils import VideoToDocError, seconds_to_ms

# 句末标点：强切分点（句号/问号/感叹号）
_STRONG_SENTENCE_ENDS = set('。！？!?')


def transcribe_audio(audio_path: Path, output_path: Path, settings: Settings, force: bool = False) -> Transcript:
    """将音频转为统一 transcript JSON。

    第一优先级是 Apple Silicon 友好的 `mlx-whisper`。`mock` 只用于
    验证非 ASR 流水线，质量报告会把它标为非真实转录。
    """

    if output_path.exists() and not force:
        return transcript_from_dict(read_json(output_path))

    backend = settings.asr_backend.lower()
    if backend in {"mlx-whisper", "mlx_whisper", "mlx"}:
        transcript = _mlx_whisper(audio_path, settings)
    elif backend == "faster-whisper":
        transcript = _faster_whisper(audio_path, settings)
    elif backend in {"qwen", "qwen3-asr", "qwen3-asr-flash"}:
        raise VideoToDocError(
        "Qwen3-ASR 后端接口已预留，但第一版默认不启用商业 API。请使用 --asr faster-whisper。"
    )
    elif backend in {"funasr", "sensevoice"}:
        raise VideoToDocError(f"{backend} 后端已预留为插件式扩展，当前版本尚未实现。")
    else:
        raise VideoToDocError(f"未知 ASR 后端：{settings.asr_backend}")

    transcript.segments = normalize_segments(transcript.segments, settings)
    transcript.segments = split_long_segments(transcript.segments, settings)
    transcript.segments = merge_short_segments(transcript.segments, settings)
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
        # 保留词级数据，normalize 只处理文本
        normalized.append(
            TranscriptSegment(
                start_ms=max(0, int(segment.start_ms)),
                end_ms=max(int(segment.start_ms), int(segment.end_ms)),
                text=text,
                confidence=segment.confidence,
                words=segment.words,
            )
        )
    return normalized


def split_long_segments(segments: list[TranscriptSegment], settings: Settings) -> list[TranscriptSegment]:
    """对超过 max_periods_per_segment 个句号的段落，按句号切分。

    优先使用词级时间戳精确定位切分点；
    若无词级数据则按字数比例线性分配。
    切分后清空子段的 words 列表（子段已不可再按词切分）。
    """
    max_periods = getattr(settings, "max_periods_per_segment", 3)
    min_chars = getattr(settings, "min_segment_chars", 30)
    if max_periods <= 0:
        return segments

    result: list[TranscriptSegment] = []
    for segment in segments:
        text = segment.text.strip()
        if not text:
            result.append(segment)
            continue

        # 按句号切分
        sentences = _split_text_into_sentences(text, max_periods, min_chars)
        if len(sentences) <= 1:
            result.append(segment)
            continue

        # 有词级时间戳：用真实时间戳定位切分点
        if segment.words:
            sub_segments = _split_with_word_timestamps(segment, sentences)
            result.extend(sub_segments)
        else:
            # 无词级时间戳：按字数比例分配
            sub_segments = _split_by_char_ratio(segment, sentences)
            result.extend(sub_segments)

    return result


def _split_with_word_timestamps(
    segment: TranscriptSegment, sentences: list[str]
) -> list[TranscriptSegment]:
    """利用词级时间戳，在切分点处用最后一个词的 end_ms 作为新段落起点。"""
    words = segment.words
    result: list[TranscriptSegment] = []

    # 把句子拼回原文，计算每个切分点在原文中的字符偏移
    # 找到每个句子结尾在 words 列表中对应的词索引
    char_offset = 0
    sentence_word_ends: list[int] = []  # 每句结尾对应的 word 索引
    for sent in sentences:
        char_offset += len(sent)
        # 在 words 中找到覆盖这个字符偏移的词
        cum_chars = 0
        end_word_idx = len(words) - 1  # 兜底
        for wi, w in enumerate(words):
            cum_chars += len(w.word)
            if cum_chars >= char_offset:
                end_word_idx = wi
                break
        sentence_word_ends.append(end_word_idx)

    # 构建子段
    start_ms = segment.start_ms
    word_idx = 0
    for i, sent in enumerate(sentences):
        end_word_idx = sentence_word_ends[i]
        # 该子段结束时间 = 对应词的 end_ms
        end_ms = words[end_word_idx].end_ms
        # 最后一句取原始结束时间
        if i == len(sentences) - 1:
            end_ms = segment.end_ms

        result.append(TranscriptSegment(
            start_ms=max(start_ms, 0),
            end_ms=max(end_ms, start_ms),
            text=sent.strip(),
            confidence=segment.confidence,
            words=[],  # 子段不再保留词级数据
        ))
        # 下一子段从该词之后开始
        start_ms = end_ms
        word_idx = end_word_idx + 1

    return result


def _split_by_char_ratio(
    segment: TranscriptSegment, sentences: list[str]
) -> list[TranscriptSegment]:
    """无词级时间戳时，按字数比例线性分配时间戳。"""
    total_chars = sum(len(s) for s in sentences)
    duration_ms = segment.end_ms - segment.start_ms
    current_ms = segment.start_ms

    result: list[TranscriptSegment] = []
    for i, sent in enumerate(sentences):
        if i == len(sentences) - 1:
            end_ms = segment.end_ms
        else:
            end_ms = segment.start_ms + int(round(
                duration_ms * (sum(len(s) for s in sentences[:i+1]) / total_chars)
            ))
        result.append(TranscriptSegment(
            start_ms=max(current_ms, 0),
            end_ms=max(end_ms, current_ms),
            text=sent.strip(),
            confidence=segment.confidence,
            words=[],
        ))
        current_ms = end_ms

    return result


def merge_short_segments(segments: list[TranscriptSegment], settings: Settings) -> list[TranscriptSegment]:
    """把低于 min_segment_chars 字数的短段合并到时间间隔最小的相邻段。

    计算短段与前后段的时间间隔，合并到间隔更小的那个。
    合并后时间区间扩展，文字拼接，清空 words。
    """
    min_chars = getattr(settings, "min_segment_chars", 30)
    if min_chars <= 0 or not segments:
        return segments

    # 从后往前处理，避免合并后索引变化
    result = list(segments)
    i = len(result) - 1
    while i >= 0:
        seg = result[i]
        if len(seg.text.strip()) >= min_chars:
            i -= 1
            continue

        # 计算与前后段的间隔
        gap_before = (seg.start_ms - result[i - 1].end_ms) if i > 0 else float("inf")
        gap_after = (result[i + 1].start_ms - seg.end_ms) if i + 1 < len(result) else float("inf")

        if gap_before <= gap_after and i > 0:
            # 合并到前一段
            prev = result[i - 1]
            result[i - 1] = TranscriptSegment(
                start_ms=prev.start_ms,
                end_ms=max(prev.end_ms, seg.end_ms),
                text=prev.text.strip() + " " + seg.text.strip(),
                confidence=prev.confidence,
                words=[],
            )
            result.pop(i)
        elif gap_after < gap_before and i + 1 < len(result):
            # 合并到后一段
            nxt = result[i + 1]
            result[i + 1] = TranscriptSegment(
                start_ms=min(seg.start_ms, nxt.start_ms),
                end_ms=nxt.end_ms,
                text=seg.text.strip() + " " + nxt.text.strip(),
                confidence=nxt.confidence,
                words=[],
            )
            result.pop(i)
        else:
            # 前后都没有，保留原段
            pass
        i -= 1

    return result


def _split_text_into_sentences(text: str, max_periods: int, min_chars: int = 30) -> list[str]:
    """按句号切分文本，每段最多 max_periods 个句号，且每段至少 min_chars 个字。

    只在句号/问号/感叹号处切分。遇到第 max_periods 个句号时，如果当前
    累计字数 >= min_chars 就切；否则跳过这个句号，等下一个满足字数条件的句号再切。
    """
    sentences: list[str] = []
    current = ""
    period_count = 0

    for char in text:
        current += char
        if char in _STRONG_SENTENCE_ENDS:
            period_count += 1
            if period_count >= max_periods and len(current) >= min_chars:
                sentences.append(current)
                current = ""
                period_count = 0

    if current.strip():
        sentences.append(current)

    return sentences


def transcript_from_dict(data: dict) -> Transcript:
    segs = []
    for item in data.get("segments", []):
        words_data = item.get("words", []) or []
        words = [
            WordTimestamp(
                start_ms=int(w["start_ms"]) if "start_ms" in w else seconds_to_ms(float(w.get("start", 0))),
                end_ms=int(w["end_ms"]) if "end_ms" in w else seconds_to_ms(float(w.get("end", 0))),
                word=str(w.get("word", "")),
            )
            for w in words_data
        ]
        start_ms = item.get("start_ms")
        if start_ms is None:
            start_ms = seconds_to_ms(float(item.get("start", 0)))
        end_ms = item.get("end_ms")
        if end_ms is None:
            end_ms = seconds_to_ms(float(item.get("end", 0)))
        segs.append(TranscriptSegment(
            start_ms=int(start_ms),
            end_ms=int(end_ms),
            text=item.get("text", "").strip(),
            confidence=item.get("confidence"),
            words=words,
        ))
    return Transcript(
        backend=data.get("backend", ""),
        language=data.get("language", "zh"),
        prompt=data.get("prompt", ""),
        metadata=data.get("metadata", {}),
        segments=segs,
    )


def _faster_whisper(audio_path: Path, settings: Settings) -> Transcript:
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ModuleNotFoundError as exc:
        raise VideoToDocError(
            "未安装 faster-whisper。请执行 `pip install faster-whisper`。"
        ) from exc

    model = WhisperModel(settings.asr_model, device="auto", compute_type="auto")
    segments, info = model.transcribe(
        str(audio_path),
        language=settings.language,
        initial_prompt=settings.prompt,
        vad_filter=True,
        word_timestamps=True,
    )
    items: list[TranscriptSegment] = []
    for segment in segments:
        confidence = None
        if getattr(segment, "avg_logprob", None) is not None:
            confidence = max(0.0, min(1.0, (float(segment.avg_logprob) + 1.5) / 1.5))
        words = [
            WordTimestamp(
                start_ms=seconds_to_ms(w.start),
                end_ms=seconds_to_ms(w.end),
                word=str(w.word),
            )
            for w in (getattr(segment, "words", None) or [])
        ]
        items.append(
            TranscriptSegment(
                start_ms=seconds_to_ms(segment.start),
                end_ms=seconds_to_ms(segment.end),
                text=segment.text,
                confidence=confidence,
                words=words,
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
            "未安装 mlx-whisper。请执行 `pip install mlx-whisper`。"
        ) from exc

    kwargs = {
        "path_or_hf_repo": settings.asr_model,
        "language": settings.language,
        "initial_prompt": settings.prompt,
        "word_timestamps": True,
    }
    try:
        result = mlx_whisper.transcribe(str(audio_path), **kwargs)
    except TypeError:
        # 兼容不同 mlx-whisper 版本的参数表。
        for key in ("initial_prompt", "word_timestamps"):
            kwargs.pop(key, None)
        result = mlx_whisper.transcribe(str(audio_path), **kwargs)

    items: list[TranscriptSegment] = []
    for segment in result.get("segments", []):
        words = [
            WordTimestamp(
                start_ms=seconds_to_ms(float(w.get("start", 0))),
                end_ms=seconds_to_ms(float(w.get("end", 0))),
                word=str(w.get("word", "")),
            )
            for w in segment.get("words", []) or []
        ]
        items.append(
            TranscriptSegment(
                start_ms=seconds_to_ms(float(segment.get("start", 0))),
                end_ms=seconds_to_ms(float(segment.get("end", 0))),
                text=str(segment.get("text", "")).strip(),
                confidence=None,
                words=words,
            )
        )
    return Transcript(
        backend="mlx-whisper",
        language=result.get("language", settings.language),
        prompt=settings.prompt,
        segments=items,
        metadata={"model": settings.asr_model},
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
