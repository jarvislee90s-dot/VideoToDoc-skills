import unittest

from videotodoc.align import align_sections
from videotodoc.models import Slide, SlideSet, Transcript, TranscriptSegment


class AlignTests(unittest.TestCase):
    def test_align_sections_matches_overlapping_segments(self):
        slides = SlideSet(
            slides=[
                Slide(1, "slides/0001.png", 0, 10000, 9000, 0.9),
                Slide(2, "slides/0002.png", 10000, 20000, 19000, 0.9),
            ]
        )
        transcript = Transcript(
            backend="mock",
            language="zh",
            segments=[
                TranscriptSegment(1000, 5000, "第一页内容", 1.0),
                TranscriptSegment(12000, 15000, "第二页内容", 1.0),
            ],
        )

        sections = align_sections(slides, transcript)

        self.assertEqual(sections[0].transcript, "第一页内容")
        self.assertEqual(sections[1].transcript, "第二页内容")

    def test_align_sections_keeps_empty_pages(self):
        slides = SlideSet(slides=[Slide(1, "slides/0001.png", 0, 10000, 9000, 0.9)])
        transcript = Transcript(backend="mock", language="zh", segments=[])

        sections = align_sections(slides, transcript)

        self.assertEqual(sections[0].transcript, "本页无讲解。")
        self.assertEqual(sections[0].notes, ["empty_transcript_match"])

    def test_align_sections_applies_sync_offset(self):
        slides = SlideSet(slides=[Slide(1, "slides/0001.png", 5000, 10000, 9000, 0.9)])
        transcript = Transcript(
            backend="mock",
            language="zh",
            segments=[TranscriptSegment(0, 3000, "需要偏移后匹配", 1.0)],
        )

        sections = align_sections(slides, transcript, sync_offset_ms=6000)

        self.assertEqual(sections[0].transcript, "需要偏移后匹配")


if __name__ == "__main__":
    unittest.main()
