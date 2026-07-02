"""Task 9: 文档生成并行化测试。"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from videotodoc.config import Settings
from videotodoc.models import Section, Slide, SlideSet, Transcript, TranscriptSegment, to_plain_dict


def _make_test_image(path: Path, color: tuple = (255, 255, 255)) -> None:
    from PIL import Image
    img = Image.new("RGB", (100, 100), color=color)
    img.save(path)


def _make_sections() -> list[Section]:
    return [
        Section(slide_index=1, image_path="", start_ms=0, end_ms=5000, capture_ms=4000, transcript="内容一", segment_indexes=[0]),
        Section(slide_index=2, image_path="", start_ms=5000, end_ms=10000, capture_ms=9000, transcript="内容二", segment_indexes=[1]),
    ]


def _make_slides(tmp_path: Path, tag: str = "orig") -> SlideSet:
    _make_test_image(tmp_path / f"s1_{tag}.png", (255, 0, 0))
    _make_test_image(tmp_path / f"s2_{tag}.png", (0, 255, 0))
    return SlideSet(slides=[
        Slide(slide_index=1, image_path=str(tmp_path / f"s1_{tag}.png"), start_ms=0, end_ms=5000,
              capture_ms=4000, confidence=0.9, hash="0000000000000001", edge_density=0.2),
        Slide(slide_index=2, image_path=str(tmp_path / f"s2_{tag}.png"), start_ms=5000, end_ms=10000,
              capture_ms=9000, confidence=0.9, hash="0000000000000002", edge_density=0.3),
    ])


class TestDocGenerationParallel:
    def test_process_video_generates_all_outputs(self, tmp_path):
        """process_video 各文档产物应正常生成（mock 掉耗时步骤）。"""
        from videotodoc.pipeline import process_video

        video_path = tmp_path / "test.mp4"
        video_path.write_bytes(b"fake video content")
        runs_dir = tmp_path / "runs"

        settings = Settings(
            asr_backend="mock",
            asr_model="mock",
            capture_mode="fast",
            scene_threshold=0.4,
            hash_threshold=8,
        )

        mock_transcript = Transcript(
            backend="mock",
            language="zh",
            segments=[
                TranscriptSegment(start_ms=0, end_ms=5000, text="第一段文字"),
                TranscriptSegment(start_ms=5000, end_ms=10000, text="第二段文字"),
            ],
        )

        def mock_extract_audio(vp, ap, settings, force=False):
            ap.parent.mkdir(parents=True, exist_ok=True)
            ap.write_bytes(b"audio")
            return ap

        def mock_transcribe(audio, tp, settings, force=False):
            return mock_transcript

        def mock_detect(vp, od, oj, settings, force=False, skip_dedupe=False):
            return _make_slides(tmp_path, "detect")

        def mock_trim(candidates, transcript, vp, td, settings):
            return _make_slides(tmp_path, "trim")

        def mock_dedupe(candidates, settings):
            return _make_slides(tmp_path, "dedupe")

        def mock_materialize(slides, output_dir):
            output_dir.mkdir(parents=True, exist_ok=True)
            for s in slides.slides:
                src = Path(s.image_path)
                dst = output_dir / f"{s.slide_index:04d}.png"
                if src.exists():
                    import shutil
                    shutil.copy2(src, dst)
                s.image_path = str(dst)
            return slides

        def mock_estimate(audio, slides, transcript, settings):
            return 0

        def mock_align(slideset, transcript, offset):
            return _make_sections()

        def mock_render_orig(title, sections, path):
            path.write_text("# original markdown", encoding="utf-8")

        def mock_render_compact(title, sections, path, mindmap_image_path=None):
            path.write_text("# compact markdown", encoding="utf-8")

        def mock_ensure_semantic(title, sections, path, mindmap_image_path=None):
            path.write_text("# semantic markdown", encoding="utf-8")

        def mock_quality_report(path, transcript, slides, sections, offset):
            path.write_text("# quality report", encoding="utf-8")

        with patch("videotodoc.pipeline.extract_audio", side_effect=mock_extract_audio), \
             patch("videotodoc.pipeline.transcribe_audio", side_effect=mock_transcribe), \
             patch("videotodoc.pipeline.detect_slides", side_effect=mock_detect), \
             patch("videotodoc.pipeline.trim_candidates_by_transcript", side_effect=mock_trim), \
             patch("videotodoc.pipeline.deduplicate_slides", side_effect=mock_dedupe), \
             patch("videotodoc.pipeline.materialize_selected_slides", side_effect=mock_materialize), \
             patch("videotodoc.pipeline.estimate_sync_offset_ms", side_effect=mock_estimate), \
             patch("videotodoc.pipeline.align_sections", side_effect=mock_align), \
             patch("videotodoc.pipeline.render_original_markdown", side_effect=mock_render_orig), \
             patch("videotodoc.pipeline.render_compact_markdown", side_effect=mock_render_compact), \
             patch("videotodoc.pipeline.ensure_semantic_markdown", side_effect=mock_ensure_semantic), \
             patch("videotodoc.pipeline.write_quality_report", side_effect=mock_quality_report):

            result = process_video(video_path, runs_dir, settings, force_rebuild={"all"})

        assert result.markdown_path.exists(), "原始 markdown 应生成"
        assert result.compact_markdown_path.exists(), "紧凑版 markdown 应生成"
        assert result.semantic_markdown_path.exists(), "整理版 markdown 应生成"
        assert result.mindmap_path is None, "pipeline 不应生成思维导图 mmd"
        assert result.mindmap_image_path is None, "pipeline 不应生成思维导图 PNG"
        assert result.docx_path is None, "pipeline 不应生成 docx"
        assert result.semantic_docx_path is None, "pipeline 不应生成整理版 docx"
        assert result.quality_report_path.exists(), "质量报告应生成"
