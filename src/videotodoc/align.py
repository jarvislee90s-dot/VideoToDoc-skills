from __future__ import annotations

from .models import Section, SlideSet, Transcript


def align_sections(slides: SlideSet, transcript: Transcript, sync_offset_ms: int = 0) -> list[Section]:
    sections: list[Section] = []
    for slide in slides.slides:
        matched_text: list[str] = []
        matched_indexes: list[int] = []
        for index, segment in enumerate(transcript.segments):
            seg_start = segment.start_ms + sync_offset_ms
            seg_end = segment.end_ms + sync_offset_ms
            if _overlaps(slide.start_ms, slide.end_ms, seg_start, seg_end):
                matched_text.append(segment.text)
                matched_indexes.append(index)
        notes: list[str] = []
        if not matched_text:
            matched_text.append("本页无讲解。")
            notes.append("empty_transcript_match")
        sections.append(
            Section(
                slide_index=slide.slide_index,
                image_path=slide.image_path,
                start_ms=slide.start_ms,
                end_ms=slide.end_ms,
                capture_ms=slide.capture_ms,
                transcript="\n\n".join(matched_text),
                segment_indexes=matched_indexes,
                notes=notes,
            )
        )
    return sections


def _overlaps(left_start: int, left_end: int, right_start: int, right_end: int) -> bool:
    return max(left_start, right_start) < min(left_end, right_end)
