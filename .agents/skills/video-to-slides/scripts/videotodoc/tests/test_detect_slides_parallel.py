"""Task 7: detect_slides 候选帧提取并行化测试。"""
from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from videotodoc.config import Settings
from videotodoc.slides import detect_slides


def _make_test_image(path: Path, color: tuple = (255, 255, 255)) -> None:
    img = Image.new("RGB", (100, 100), color=color)
    img.save(path)


class TestDetectSlidesParallel:
    def test_parallel_extraction_is_faster_than_serial(self, tmp_path):
        """带延迟模拟的 extract_frame 并行执行应快于串行。"""
        video_path = tmp_path / "test.mp4"
        video_path.write_bytes(b"fake video")

        output_dir = tmp_path / "slides"
        output_json = tmp_path / "slides.json"
        candidates_dir = tmp_path / "slide_candidates"

        settings = Settings(
            capture_mode="fast",
            scene_threshold=0.3,
            hash_threshold=8,
            fallback_interval_sec=5,
            min_slide_seconds=1,
        )

        delay_per_frame = 0.1
        num_candidates = 5

        def mock_probe_duration(vp):
            return 30000

        def mock_detect_scene(vp, threshold):
            return [i * 5000 for i in range(1, num_candidates)]

        extract_calls: list[float] = []

        def mock_extract_frame(vp, capture_ms, output_path, precise=False):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            extract_calls.append(time.time())
            time.sleep(delay_per_frame)
            _make_test_image(output_path, (200, 200, 200))

        with patch("videotodoc.slides.probe_duration_ms", side_effect=mock_probe_duration), \
             patch("videotodoc.slides.detect_scene_changes", side_effect=mock_detect_scene), \
             patch("videotodoc.slides.extract_frame", side_effect=mock_extract_frame), \
             patch("videotodoc.slides.refine_selected_slides", side_effect=lambda vp, slides, od, s, cd=None: slides):

            start = time.time()
            result = detect_slides(video_path, output_dir, output_json, settings, force=True, skip_dedupe=True)
            elapsed = time.time() - start

        serial_time = delay_per_frame * num_candidates
        assert elapsed < serial_time * 0.7, (
            f"并行执行应明显快于串行（串行≈{serial_time:.2f}s，实际={elapsed:.2f}s）"
        )
        assert len(extract_calls) >= num_candidates

    def test_parallel_preserves_order(self, tmp_path):
        """并行提取后结果顺序应与串行一致。"""
        video_path = tmp_path / "test.mp4"
        video_path.write_bytes(b"fake video")

        output_dir = tmp_path / "slides"
        output_json = tmp_path / "slides.json"

        settings = Settings(
            capture_mode="fast",
            scene_threshold=0.3,
            hash_threshold=2,
            fallback_interval_sec=10,
            min_slide_seconds=1,
            keep_all_candidates=True,
        )

        colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (255, 0, 255)]

        def mock_probe_duration(vp):
            return 55000

        def mock_detect_scene(vp, threshold):
            return [10000, 20000, 30000, 40000]

        call_idx = [0]

        def mock_extract_frame(vp, capture_ms, output_path, precise=False):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            idx = min(call_idx[0], len(colors) - 1)
            call_idx[0] += 1
            _make_test_image(output_path, colors[idx])

        with patch("videotodoc.slides.probe_duration_ms", side_effect=mock_probe_duration), \
             patch("videotodoc.slides.detect_scene_changes", side_effect=mock_detect_scene), \
             patch("videotodoc.slides.extract_frame", side_effect=mock_extract_frame), \
             patch("videotodoc.slides.refine_selected_slides", side_effect=lambda vp, slides, od, s, cd=None: slides):

            result = detect_slides(video_path, output_dir, output_json, settings, force=True, skip_dedupe=True)

        assert len(result.slides) == 5
        for i, slide in enumerate(result.slides):
            assert slide.slide_index == i + 1
            assert slide.start_ms <= slide.capture_ms <= slide.end_ms
