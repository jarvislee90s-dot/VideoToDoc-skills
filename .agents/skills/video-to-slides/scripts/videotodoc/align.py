from __future__ import annotations

from .models import Section, SlideSet, Transcript


def align_sections(slides: SlideSet, transcript: Transcript, sync_offset_ms: int = 0) -> list[Section]:
    """将截图与 ASR 转录按时间轴对齐。

    双向去重后的对齐规则：
    - 每张图的 capture_ms 是一个时间点，落在某个 ASR 段的 [start, end) 内
    - 该图归属到 capture_ms 所在的段，以及该图与前一张图之间所有没有图的段
    - 即：一张图可以对应多段话（方向 B：一图多段→图归到这些段的最后一页）
    - 每段话只出现在一页中（不会重复）
    """
    if not slides.slides or not transcript.segments:
        return []

    # 为每个 ASR 段确定它归属哪张图
    # 方法：capture_ms 落在哪个段，那张图就是这个段及之前无图段的"所属图"
    segment_to_slide: dict[int, int] = {}  # segment_index → slide_index
    for seg_idx, segment in enumerate(transcript.segments):
        seg_start = segment.start_ms + sync_offset_ms
        seg_end = segment.end_ms + sync_offset_ms
        for slide in slides.slides:
            if seg_start <= slide.capture_ms < seg_end:
                segment_to_slide[seg_idx] = slide.slide_index
                break

    # 对于没有直接匹配到图的段，归到最近的后面那张图
    # 如果后面也没有图，归到最近的前面那张图
    for seg_idx in range(len(transcript.segments)):
        if seg_idx in segment_to_slide:
            continue
        # 找后面的
        found = False
        for later_idx in range(seg_idx + 1, len(transcript.segments)):
            if later_idx in segment_to_slide:
                segment_to_slide[seg_idx] = segment_to_slide[later_idx]
                found = True
                break
        if not found:
            # 找前面的
            for earlier_idx in range(seg_idx - 1, -1, -1):
                if earlier_idx in segment_to_slide:
                    segment_to_slide[seg_idx] = segment_to_slide[earlier_idx]
                    break

    # 反向映射：slide_index → 匹配的 segment indexes
    slide_to_segments: dict[int, list[int]] = {}
    for seg_idx, s_idx in segment_to_slide.items():
        slide_to_segments.setdefault(s_idx, []).append(seg_idx)
    # 排序保证顺序
    for s_idx in slide_to_segments:
        slide_to_segments[s_idx].sort()

    # 构建 sections
    sections: list[Section] = []
    for slide in slides.slides:
        seg_indexes = slide_to_segments.get(slide.slide_index, [])
        if seg_indexes:
            matched_text = [transcript.segments[i].text for i in seg_indexes]
        else:
            matched_text = ["本页无讲解。"]
        notes: list[str] = []
        if not seg_indexes:
            notes.append("empty_transcript_match")
        sections.append(
            Section(
                slide_index=slide.slide_index,
                image_path=slide.image_path,
                start_ms=slide.start_ms,
                end_ms=slide.end_ms,
                capture_ms=slide.capture_ms,
                transcript="\n\n".join(matched_text),
                segment_indexes=seg_indexes,
                notes=notes,
            )
        )
    return sections
