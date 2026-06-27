"""Task 4: OCR 缓存到 Slide 对象 + tempfile 临时帧目录测试。"""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

from videotodoc.config import Settings
from videotodoc.models import DedupeStats, Slide
from videotodoc.slides import choose_capture_time, is_near_duplicate


def _make_test_image(path: Path, color: tuple = (255, 255, 255)) -> None:
    img = Image.new("RGB", (100, 100), color=color)
    img.save(path)


class TestSlideOcrTextField:
    def test_slide_has_ocr_text_field_default_none(self):
        """Slide 新增 ocr_text 字段，默认值为 None，向后兼容。"""
        slide = Slide(
            slide_index=1,
            image_path="test.png",
            start_ms=0,
            end_ms=1000,
            capture_ms=500,
            confidence=0.8,
        )
        assert slide.ocr_text is None
        assert slide.hash is None
        assert slide.edge_density is None

    def test_slide_accepts_ocr_text_value(self):
        """Slide 可以接受 ocr_text 参数。"""
        slide = Slide(
            slide_index=1,
            image_path="test.png",
            start_ms=0,
            end_ms=1000,
            capture_ms=500,
            confidence=0.8,
            ocr_text="hello world",
        )
        assert slide.ocr_text == "hello world"

    def test_slide_positional_args_still_work(self):
        """位置参数构造 Slide 仍然工作（向后兼容）。"""
        slide = Slide(1, "test.png", 0, 1000, 500, 0.8)
        assert slide.slide_index == 1
        assert slide.image_path == "test.png"
        assert slide.start_ms == 0
        assert slide.end_ms == 1000
        assert slide.capture_ms == 500
        assert slide.confidence == 0.8
        assert slide.ocr_text is None


class TestIsNearDuplicateCachedOcr:
    def test_is_near_duplicate_uses_cached_ocr_text(self, tmp_path):
        """当 current.ocr_text 和 previous.ocr_text 已缓存时，不调用 extract_text。"""
        img1 = tmp_path / "img1.png"
        img2 = tmp_path / "img2.png"
        _make_test_image(img1, (255, 255, 255))
        _make_test_image(img2, (255, 255, 255))

        from videotodoc.slides import dhash
        h1 = dhash(img1)
        h2 = dhash(img2)

        current = Slide(
            slide_index=2,
            image_path=str(img2),
            start_ms=1000,
            end_ms=2000,
            capture_ms=1500,
            confidence=0.8,
            hash=f"{h2:016x}",
            edge_density=0.1,
            ocr_text="same text content",
        )
        previous = Slide(
            slide_index=1,
            image_path=str(img1),
            start_ms=0,
            end_ms=1000,
            capture_ms=500,
            confidence=0.8,
            hash=f"{h1:016x}",
            edge_density=0.1,
            ocr_text="same text content",
        )

        settings = Settings(
            hash_threshold=8,
            ocr_dedupe=True,
            ocr_similarity_threshold=0.9,
            duplicate_change_threshold=0.005,
            different_change_threshold=0.5,
            different_hash_threshold=16,
        )

        with patch("videotodoc.slides.extract_text") as mock_extract:
            mock_extract.return_value = "different text"
            result = is_near_duplicate(current, previous, settings.hash_threshold, settings)
            mock_extract.assert_not_called()

    def test_is_near_duplicate_accepts_slide_objects(self, tmp_path):
        """is_near_duplicate 新签名接受 Slide 对象而非 Path。"""
        img1 = tmp_path / "img1.png"
        img2 = tmp_path / "img2.png"
        _make_test_image(img1, (255, 255, 255))
        _make_test_image(img2, (0, 0, 0))

        from videotodoc.slides import dhash
        h1 = dhash(img1)
        h2 = dhash(img2)

        current = Slide(
            slide_index=2,
            image_path=str(img2),
            start_ms=1000,
            end_ms=2000,
            capture_ms=1500,
            confidence=0.8,
            hash=f"{h2:016x}",
            edge_density=0.5,
        )
        previous = Slide(
            slide_index=1,
            image_path=str(img1),
            start_ms=0,
            end_ms=1000,
            capture_ms=500,
            confidence=0.8,
            hash=f"{h1:016x}",
            edge_density=0.1,
        )

        settings = Settings(hash_threshold=8)
        stats = DedupeStats()
        result = is_near_duplicate(current, previous, settings.hash_threshold, settings, stats)
        assert isinstance(result, bool)


class TestChooseCaptureTimeTempdir:
    def test_choose_capture_time_uses_tempdir_not_video_parent(self, tmp_path):
        """choose_capture_time 使用 tempfile.mkdtemp，不在视频父目录创建 .videotodoc_tmp_frames。"""
        video_dir = tmp_path / "video_dir"
        video_dir.mkdir()
        video_path = video_dir / "test.mp4"
        video_path.write_bytes(b"fake video")

        tmp_frames_dir = video_dir / ".videotodoc_tmp_frames"

        def mock_extract_frame(vp, capture_ms, output_path, precise=True):
            _make_test_image(output_path, (100, 100, 100))

        with patch("videotodoc.slides.extract_frame", side_effect=mock_extract_frame):
            with patch("videotodoc.slides.probe_duration_ms", return_value=10000):
                settings = Settings(
                    stability_window_seconds=0.3,
                    refine_fps=10,
                    capture_margin_ms=100,
                    hash_threshold=8,
                )
                capture_ms, confidence = choose_capture_time(video_path, 0, 1000, settings)

        assert not tmp_frames_dir.exists(), (
            f".videotodoc_tmp_frames 不应在视频父目录创建，但发现: {tmp_frames_dir}"
        )
        assert isinstance(capture_ms, int)
        assert isinstance(confidence, float)
