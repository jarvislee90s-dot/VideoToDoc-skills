from __future__ import annotations

from .models import Section, SlideSet, Transcript


# 句末标点：在区间边界回溯断句，避免切开句子成分（与 review 句法硬标准精神一致）
_SENTENCE_END = set("。！？；!?;")


def _char_pos_for_ms(seg_text: str, seg_start_ms: int, seg_end_ms: int, target_ms: int) -> int:
    """按时间线性插值估算 target_ms 在 seg_text 中对应的字符位置。

    合并段无字级时间戳，用段级时间线性插值估算，不精确但足够定位断句点。
    """
    if seg_end_ms <= seg_start_ms:
        return 0
    ratio = (target_ms - seg_start_ms) / (seg_end_ms - seg_start_ms)
    ratio = max(0.0, min(1.0, ratio))
    return int(ratio * len(seg_text))


def _snap_to_sentence_end(seg_text: str, pos: int) -> int:
    """从 pos 向前回溯到最近的句末标点之后，找不到返回 pos。

    保证切分点落在句子成分之间，不切断主谓宾。
    """
    upper = min(pos, len(seg_text))
    for i in range(upper - 1, -1, -1):
        if seg_text[i] in _SENTENCE_END:
            return i + 1
    return pos


def align_sections(slides: SlideSet, transcript: Transcript, sync_offset_ms: int = 0) -> list[Section]:
    """将截图与 ASR 转录按时间轴对齐。

    按截图的 capture_ms 作为分页点：
    - segment 仅包含一张图的 capture_ms → 整段归该图（保留原语义）。
    - segment 跨越多张图 → 在相邻 capture 的中点切分文本，切点回溯到最近句末标点，
      保证不切断主谓宾；切点单调递增，不重复不丢失。每段归对应图。
    - 无图认领的 segment → 归最近图（保留原逻辑：后面的优先，否则前面）。
    """
    if not slides.slides or not transcript.segments:
        return []

    slides_list = slides.slides
    # capture → slide_index 映射（同 ms 取后定义者）
    capture_to_slide: dict[int, int] = {}
    for s in slides_list:
        capture_to_slide[s.capture_ms + sync_offset_ms] = s.slide_index
    captures_sorted = sorted(capture_to_slide.keys())

    page_text: dict[int, list[str]] = {s.slide_index: [] for s in slides_list}
    page_segs: dict[int, list[int]] = {s.slide_index: [] for s in slides_list}

    for seg_idx, seg in enumerate(transcript.segments):
        seg_s = seg.start_ms
        seg_e = seg.end_ms
        # 该 segment 包含的 capture_ms（落在 [seg_s, seg_e) 内）
        inner = [c for c in captures_sorted if seg_s <= c < seg_e]

        if not inner:
            # 无图认领 → 归最近图（后面的优先，否则前面）
            target = None
            for c in captures_sorted:
                if c >= seg_e:
                    target = capture_to_slide[c]
                    break
            if target is None:
                for c in reversed(captures_sorted):
                    if c <= seg_s:
                        target = capture_to_slide[c]
                        break
            if target is None:
                target = slides_list[0].slide_index
            page_text[target].append(seg.text)
            page_segs[target].append(seg_idx)
        elif len(inner) == 1:
            sid = capture_to_slide[inner[0]]
            page_text[sid].append(seg.text)
            page_segs[sid].append(seg_idx)
        else:
            # 多图认领 → 在相邻 capture 中点切分，回溯句号，切点单调递增
            cut_points: list[int] = []
            last_cut = 0
            for i in range(len(inner) - 1):
                mid = (inner[i] + inner[i + 1]) / 2
                pos = _char_pos_for_ms(seg.text, seg_s, seg_e, mid)
                pos = _snap_to_sentence_end(seg.text, pos)
                if pos <= last_cut:
                    # 不能倒退：至少前进 1 字，避免空段
                    pos = min(last_cut + 1, len(seg.text))
                cut_points.append(pos)
                last_cut = pos
            prev = 0
            for i, c in enumerate(inner):
                sid = capture_to_slide[c]
                end = cut_points[i] if i < len(cut_points) else len(seg.text)
                piece = seg.text[prev:end].strip()
                prev = end
                if piece:
                    page_text[sid].append(piece)
                    page_segs[sid].append(seg_idx)

    sections: list[Section] = []
    for slide in slides_list:
        sid = slide.slide_index
        texts = [t for t in page_text[sid] if t]
        matched = "\n\n".join(texts) if texts else "本页无讲解。"
        notes: list[str] = [] if page_segs[sid] else ["empty_transcript_match"]
        sections.append(
            Section(
                slide_index=sid,
                image_path=slide.image_path,
                start_ms=slide.start_ms,
                end_ms=slide.end_ms,
                capture_ms=slide.capture_ms,
                transcript=matched,
                segment_indexes=page_segs[sid],
                notes=notes,
            )
        )
    return sections
