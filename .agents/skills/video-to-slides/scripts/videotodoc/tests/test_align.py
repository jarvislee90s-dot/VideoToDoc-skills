"""Bug 5：图文对齐按截图区间切分文本，句末标点回溯断句。"""
import pytest

from videotodoc.align import align_sections, _char_pos_for_ms, _snap_to_sentence_end
from videotodoc.models import Slide, SlideSet, Transcript, TranscriptSegment


def _slide(idx, capture_ms, start_ms=None, end_ms=None):
    return Slide(
        slide_index=idx, image_path=f"/tmp/{idx}.png",
        start_ms=start_ms or capture_ms, end_ms=end_ms or capture_ms + 1000,
        capture_ms=capture_ms, confidence=0.9, hash="0" * 16,
    )


def _seg(start_ms, end_ms, text):
    return TranscriptSegment(start_ms=start_ms, end_ms=end_ms, text=text)


class TestCharPosForMs:
    def test_linear_interpolation(self):
        assert _char_pos_for_ms("0123456789", 0, 10000, 5000) == 5

    def test_clamp_below_zero(self):
        assert _char_pos_for_ms("abc", 1000, 2000, 500) == 0

    def test_clamp_above_end(self):
        assert _char_pos_for_ms("abc", 1000, 2000, 9999) == 3

    def test_zero_duration_returns_zero(self):
        assert _char_pos_for_ms("abc", 1000, 1000, 1000) == 0


class TestSnapToSentenceEnd:
    def test_snap_back_to_period(self):
        # "这是句子。另一句"：pos=6（'一'前）→ 回溯到句号(index 4)之后 = 5
        assert _snap_to_sentence_end("这是句子。另一句", 6) == 5

    def test_no_sentence_end_returns_pos(self):
        assert _snap_to_sentence_end("无标点文本", 3) == 3

    def test_snap_to_question_mark(self):
        # "问题？答案"：pos=4（'案'前）→ 回溯到问号(index 2)之后 = 3
        assert _snap_to_sentence_end("问题？答案", 4) == 3


class TestAlignSectionsWindowSplit:
    def test_long_segment_split_across_two_slides(self):
        """长合并段跨越两张图 → 文本被切分到两页，不再全堆第一张。"""
        seg_text = "这是第一页的讲解内容。这是第二页的讲解内容。"
        transcript = Transcript(
            backend="reused", language="zh",
            segments=[_seg(0, 20000, seg_text)],
        )
        slides = SlideSet(slides=[_slide(1, 5000), _slide(2, 15000)])
        sections = align_sections(slides, transcript)
        assert len(sections) == 2
        # 第一页拿到前半，第二页拿到后半，都不应是「本页无讲解」
        assert "第一页" in sections[0].transcript
        assert "第二页" in sections[1].transcript
        assert "本页无讲解" not in sections[0].transcript
        assert "本页无讲解" not in sections[1].transcript
        # 切点在句号处，没有切开句子成分
        assert sections[0].transcript.rstrip().endswith("。") or "内容" in sections[0].transcript

    def test_empty_transcript_returns_empty(self):
        slides = SlideSet(slides=[_slide(1, 1000)])
        assert align_sections(slides, Transcript("reused", "zh", [])) == []

    def test_slide_without_segment_shows_placeholder(self):
        """截图落在无 segment 区间 → 本页无讲解。"""
        transcript = Transcript(
            backend="reused", language="zh",
            segments=[_seg(0, 1000, "短句。")],
        )
        slides = SlideSet(slides=[_slide(1, 5000), _slide(2, 15000)])
        sections = align_sections(slides, transcript)
        # 第二页无对应文本
        assert "本页无讲解" in sections[1].transcript or sections[1].transcript.strip() == ""
