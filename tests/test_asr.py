import unittest

from videotodoc.asr import normalize_segments, transcript_from_dict
from videotodoc.config import Settings
from videotodoc.models import TranscriptSegment


class AsrTests(unittest.TestCase):
    def test_normalize_segments_applies_terms_and_low_confidence_marker(self):
        settings = Settings(terms={"github": "GitHub"}, low_confidence_threshold=0.8)
        segments = [TranscriptSegment(0, 1000, "github 大于等于 3", 0.5)]

        normalized = normalize_segments(segments, settings)

        self.assertEqual(normalized[0].text, "[低置信度] GitHub ≥ 3")

    def test_transcript_from_dict_roundtrip_shape(self):
        transcript = transcript_from_dict(
            {
                "backend": "mock",
                "language": "zh",
                "segments": [{"start_ms": 1, "end_ms": 2, "text": "hi", "confidence": 1.0}],
            }
        )

        self.assertEqual(transcript.backend, "mock")
        self.assertEqual(transcript.segments[0].start_ms, 1)


if __name__ == "__main__":
    unittest.main()
