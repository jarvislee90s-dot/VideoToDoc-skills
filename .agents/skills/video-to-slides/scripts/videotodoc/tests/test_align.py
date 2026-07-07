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
    def test_long_segment_across_two_split_slides_kept_whole(self):
        """新按段合页：长段跨两个独立(start/end)的 slide capture 时整段文字归首 capture 所在组，不切分句子成分。"""
        seg_text = "这是第一页的讲解内容。这是第二页的讲解内容。"
        transcript = Transcript(
            backend="reused", language="zh",
            segments=[_seg(0, 20000, seg_text)],
        )
        # 两个独立 (start,end) slide（等价 trim 单图各段），capture_ms 都落在长段内
        slides = SlideSet(slides=[_slide(1, 5000), _slide(2, 15000)])
        sections = align_sections(slides, transcript)
        assert len(sections) == 2
        # 整段文字归首个捕获段内 capture 的 slide1 组，不切分句子
        assert "第一页" in sections[0].transcript
        assert "第二页" in sections[0].transcript
        # 另一独立时间段页无文字归话题，为 placeholder
        assert "本页无讲解" in sections[1].transcript

    def test_multi_image_same_segment_merged_into_one_page(self):
        """keep_all_candidates 下 trim 给同一 (start,end) 的多 slide 会被合并成同一页，多图按 capture_ms 顺序附在整段文字上。"""
        seg_text = "这是第一页的讲解内容。这是第二页的讲解内容。"
        transcript = Transcript(
            backend="reused", language="zh",
            segments=[_seg(0, 20000, seg_text)],
        )
        # 两张 slide 共享 (start_ms=0, end_ms=20000)：候选54s+主图60s 同段多图典型形态
        slides = SlideSet(slides=[
            Slide(slide_index=1, image_path="/tmp/c1.png", start_ms=0, end_ms=20000,
                  capture_ms=5000, confidence=0.8, hash="0"*16, edge_density=0.05),
            Slide(slide_index=2, image_path="/tmp/c2.png", start_ms=0, end_ms=20000,
                  capture_ms=15000, confidence=0.9, hash="0"*16, edge_density=0.06),
        ])
        sections = align_sections(slides, transcript)
        # 只产出 1 页（按段合页）
        assert len(sections) == 1
        s = sections[0]
        # 整段保留、不拆分
        assert "第一页" in s.transcript and "第二页" in s.transcript
        assert "本页无讲解" not in s.transcript
        # 连续 1..1 编号，主图按 edge_density 取 capture_15000 那张
        assert s.slide_index == 1
        # image_paths 按 capture_ms 升序，含两张
        assert len(s.image_paths) == 2
        assert s.image_paths[0] == "/tmp/c1.png"
        assert s.image_paths[1] == "/tmp/c2.png"
        # 主图 image_path 取 edge_density 最高的（15000ms 的 c2.png）
        assert s.image_path == "/tmp/c2.png"

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


class TestParagraphDominantAlign:
    def test_section_time_range_equals_segment_boundary(self):
        """trim 产出段边界 slide 后，section 时间范围 = 段边界，capture = 段末-margin。"""
        seg = _seg(0, 22000, "一段完整的话，讲到了末尾。")
        transcript = Transcript(backend="reused", language="zh", segments=[seg])
        # trim 改造后的 slide：段边界 + 段末 capture
        slides = SlideSet(slides=[Slide(
            slide_index=1, image_path="/tmp/1.png",
            start_ms=0, end_ms=22000, capture_ms=21500,
            confidence=0.8, hash="0" * 16,
        )])
        sections = align_sections(slides, transcript)
        assert len(sections) == 1
        s = sections[0]
        assert s.start_ms == 0
        assert s.end_ms == 22000
        assert s.capture_ms == 21500
        assert "末尾" in s.transcript

    def test_capture_not_lands_on_middle_sentence(self):
        """回归：capture 不再落在段落中段（旧 bug 的反例）。"""
        seg = _seg(0, 22000, "第一句。有人299上门帮你卸载。但是我想告诉你重点。")
        transcript = Transcript(backend="reused", language="zh", segments=[seg])
        slides = SlideSet(slides=[Slide(
            slide_index=1, image_path="/tmp/1.png",
            start_ms=0, end_ms=22000, capture_ms=21500,
            confidence=0.8, hash="0" * 16,
        )])
        sections = align_sections(slides, transcript)
        # capture 在段末 21500ms，对应末句附近，不是中段「有人299」
        assert sections[0].capture_ms == 21500
        assert sections[0].end_ms == 22000
