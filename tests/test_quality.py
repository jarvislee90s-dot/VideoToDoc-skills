import tempfile
import unittest
from pathlib import Path

from videotodoc.models import Section, Slide, SlideSet, Transcript, TranscriptSegment
from videotodoc.quality import write_quality_report


class QualityTests(unittest.TestCase):
    def test_quality_report_flags_mock_and_few_slides(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "quality_report.md"
            transcript = Transcript("mock", "zh", [TranscriptSegment(0, 1000, "测试", 1.0)])
            slides = SlideSet([Slide(1, "slides/0001.png", 0, 1000, 900, 0.9)], {"candidate_count": 1})
            sections = [Section(1, "slides/0001.png", 0, 1000, 900, "测试", [0])]

            write_quality_report(output, transcript, slides, sections, 0)

            text = output.read_text(encoding="utf-8")
            self.assertIn("mock ASR", text)
            self.assertIn("最终截图数量不超过 3 页", text)


if __name__ == "__main__":
    unittest.main()
