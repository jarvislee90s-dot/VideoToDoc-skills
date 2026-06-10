import unittest

from videotodoc.config import Settings
from videotodoc.ocr import normalize_ocr_text, text_similarity
from videotodoc.models import DedupeStats
from videotodoc.slides import _build_boundaries, _candidate_points, _is_duplicate, hamming_distance, is_near_duplicate


class SlideTests(unittest.TestCase):
    def test_build_boundaries_filters_dense_changes(self):
        boundaries = _build_boundaries([1000, 1200, 3000], duration_ms=5000, min_slide_seconds=1.0)

        self.assertEqual(boundaries, [(0, 1000), (1000, 3000), (3000, 5000)])

    def test_hamming_distance(self):
        self.assertEqual(hamming_distance(0b1010, 0b0011), 2)

    def test_ocr_text_similarity_helpers(self):
        left = normalize_ocr_text(" 买入过于虚值的期权 ")
        right = normalize_ocr_text("买入过于虚值的期权")

        self.assertGreater(text_similarity(left, right), 0.95)

    def test_dedupe_stats_defaults(self):
        stats = DedupeStats()

        self.assertEqual(stats.ocr_checks, 0)

    def test_is_duplicate_uses_threshold(self):
        self.assertTrue(_is_duplicate(0b1010, [0b0010], threshold=1))
        self.assertFalse(_is_duplicate(0b1010, [0b0000], threshold=1))

    def test_candidate_points_adds_fallback_in_fine_mode(self):
        settings = Settings(capture_mode="fine", fallback_interval_sec=10)

        points = _candidate_points([5000], duration_ms=25000, settings=settings)

        self.assertEqual(points, [5000, 10000, 20000])

    def test_candidate_points_adds_fallback_in_complete_mode(self):
        settings = Settings(capture_mode="complete", fallback_interval_sec=10)

        points = _candidate_points([5000], duration_ms=25000, settings=settings)

        self.assertEqual(points, [5000, 10000, 20000])


if __name__ == "__main__":
    unittest.main()
