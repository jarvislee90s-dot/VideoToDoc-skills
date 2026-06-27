"""时长密度函数 + 分段草案启发式 + confirmed 格式校验。"""
from __future__ import annotations


def capture_interval_for_duration(duration_sec: float) -> int:
    """根据视频时长返回初始截图间隔（秒）。

    duration ≤ 5min  → 15s
    duration ≤ 15min → 20s
    duration ≤ 30min → 30s
    duration > 30min → 40s
    """
    if duration_sec <= 300:
        return 15
    if duration_sec <= 900:
        return 20
    if duration_sec <= 1800:
        return 30
    return 40

from typing import Any

from .models import Slide, SlideSet, Transcript

_STEP_WORDS = ("第一步", "第二步", "第三步", "首先", "然后", "接下来", "操作", "步骤", "点击", "输入")


def _has_step_words(text: str) -> bool:
    return any(w in text for w in _STEP_WORDS)


def generate_pending_segments(
    candidates: SlideSet,
    transcript: Transcript,
    duration_sec: float,
    max_segment_chars: int = 400,
    min_segment_chars: int = 30,
) -> dict[str, Any]:
    """基于 transcript 内容密度生成分段草案。

    分段边界由 transcript 内容决定，不由候选图 capture_ms 决定。
    启发式规则：
    1. 以 transcript segment 边界为初始切分点
    2. 贪心合并相邻片段：只要合并后总字数 <= max_segment_chars 就合并（不检查文本相似度，步骤词不阻止合并）
    3. 单段字数 > max_segment_chars → 标记 split
    4. 非首段且字数 < min_segment_chars 且无步骤词 → 标记 merge 到前一段
    5. 其余段标记 keep
    6. 候选图 slide_ids 记录在段内，但不决定边界
    7. 步骤词只影响 suggested_action 标签（含步骤词的短段保持 keep），不影响实际合并
    """
    interval = capture_interval_for_duration(duration_sec)

    if not transcript.segments:
        return {"video_title": "", "duration_sec": int(duration_sec),
                "capture_interval_sec": interval, "segments": []}

    # 以 transcript segment 为初始片段
    raw_segments = []
    for seg in transcript.segments:
        raw_segments.append({
            "start_ms": seg.start_ms,
            "end_ms": seg.end_ms,
            "text": seg.text,
        })

    # 合并相邻片段：只要合并后不超过 max_segment_chars 就合并
    # 步骤词只影响 suggested_action 标签，不影响实际合并
    merged: list[dict] = []
    for seg in raw_segments:
        if merged:
            prev = merged[-1]
            combined_text = prev["text"] + seg["text"]
            if len(combined_text) <= max_segment_chars:
                prev["end_ms"] = seg["end_ms"]
                prev["text"] = combined_text
                continue
        merged.append(dict(seg))

    # 为每个段关联候选图
    segments = []
    for i, seg in enumerate(merged, start=1):
        char_count = len(seg["text"])
        # 找该时间范围内的候选图
        slide_ids = [s.slide_index for s in candidates.slides
                     if seg["start_ms"] <= s.capture_ms < seg["end_ms"]]
        action = "keep"
        extra = {}
        if char_count > max_segment_chars:
            action = "split"
        elif i > 1 and char_count < min_segment_chars and not _has_step_words(seg["text"]):
            action = "merge"
            extra["merge_into"] = f"s{i - 1:02d}"
        segments.append({
            "id": f"s{i:02d}",
            "start_ms": seg["start_ms"],
            "end_ms": seg["end_ms"],
            "label": seg["text"][:20].strip(),
            "suggested_action": action,
            "candidate_slide_ids": slide_ids,
            "reason": f"字数{char_count}，时长{(seg['end_ms'] - seg['start_ms']) / 1000:.0f}s",
            "transcript_preview": seg["text"][:80],
            "char_count": char_count,
            **extra,
        })

    return {
        "video_title": "",
        "duration_sec": int(duration_sec),
        "capture_interval_sec": interval,
        "segments": segments,
    }


def validate_confirmed_segments(data: dict[str, Any]) -> bool:
    """校验 agent 写回的 confirmed_segments.json 格式。"""
    segments = data.get("segments")
    if not segments or not isinstance(segments, list):
        return False
    ids = {s.get("id") for s in segments}
    for s in segments:
        if not all(k in s for k in ("id", "start_ms", "end_ms", "label", "suggested_action")):
            return False
        action = s["suggested_action"]
        if action == "merge" and s.get("merge_into") not in ids:
            return False
        if action == "split" and "split_at" not in s:
            return False
    return True
