"""Task 5: 去重阈值配置化 + choose_capture_time 优化测试。"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

from videotodoc.config import Settings
from videotodoc.models import DedupeStats, Slide
from videotodoc.slides import is_near_duplicate


def _make_test_image(path: Path, color: tuple = (255, 255, 255)) -> None:
    img = Image.new("RGB", (100, 100), color=color)
    img.save(path)


def _make_similar_images_with_change(path1: Path, path2: Path, change_fraction: float = 0.05) -> None:
    """创建两张大部分相同但有一定比例像素不同的图片。"""
    img1 = Image.new("RGB", (100, 100), color=(255, 255, 255))
    img2 = img1.copy()
    draw = ImageDraw.Draw(img2)
    total_pixels = 100 * 100
    changed_pixels = int(total_pixels * change_fraction)
    region_size = int(changed_pixels ** 0.5)
    region_size = max(1, min(region_size, 100))
    draw.rectangle([0, 0, region_size - 1, region_size - 1], fill=(0, 0, 0))
    img1.save(path1)
    img2.save(path2)


class TestChangeRatioThreshold:
    def test_change_ratio_uses_config_not_hardcoded(self, tmp_path):
        """different_change_threshold 配置项应影响 is_near_duplicate 判定，
        特别是在 OCR 路径中原先硬编码 0.12 的位置。"""
        img1 = tmp_path / "a.png"
        img2 = tmp_path / "b.png"
        _make_similar_images_with_change(img1, img2, change_fraction=0.05)

        from videotodoc.slides import dhash
        h1 = dhash(img1)
        h2 = dhash(img2)

        current = Slide(
            slide_index=2, image_path=str(img2),
            start_ms=1000, end_ms=2000, capture_ms=1500, confidence=0.8,
            hash=f"{h2:016x}", edge_density=0.3, ocr_text="identical slide text",
        )
        previous = Slide(
            slide_index=1, image_path=str(img1),
            start_ms=0, end_ms=1000, capture_ms=500, confidence=0.8,
            hash=f"{h1:016x}", edge_density=0.3, ocr_text="identical slide text",
        )

        settings_strict = Settings(
            hash_threshold=64,
            ocr_dedupe=True,
            ocr_similarity_threshold=0.9,
            different_change_threshold=0.01,
            different_hash_threshold=64,
            duplicate_change_threshold=0.001,
        )
        settings_lenient = Settings(
            hash_threshold=64,
            ocr_dedupe=True,
            ocr_similarity_threshold=0.9,
            different_change_threshold=0.5,
            different_hash_threshold=64,
            duplicate_change_threshold=0.001,
        )

        result_strict = is_near_duplicate(current, previous, 64, settings_strict)
        result_lenient = is_near_duplicate(current, previous, 64, settings_lenient)

        assert result_strict != result_lenient, (
            f"different_change_threshold 配置应影响判定结果: "
            f"strict={result_strict}, lenient={result_lenient}"
        )

    def test_is_near_duplicate_slide_signature_works(self, tmp_path):
        """is_near_duplicate(current: Slide, previous: Slide, ...) 新签名可用。"""
        img1 = tmp_path / "x.png"
        img2 = tmp_path / "y.png"
        _make_test_image(img1, (255, 255, 255))
        _make_test_image(img2, (0, 0, 0))

        from videotodoc.slides import dhash
        current = Slide(
            slide_index=2, image_path=str(img2),
            start_ms=1000, end_ms=2000, capture_ms=1500, confidence=0.8,
            hash=f"{dhash(img2):016x}", edge_density=0.5,
        )
        previous = Slide(
            slide_index=1, image_path=str(img1),
            start_ms=0, end_ms=1000, capture_ms=500, confidence=0.8,
            hash=f"{dhash(img1):016x}", edge_density=0.1,
        )
        settings = Settings(hash_threshold=8)
        stats = DedupeStats()

        result = is_near_duplicate(current, previous, settings.hash_threshold, settings, stats)
        assert isinstance(result, bool)
