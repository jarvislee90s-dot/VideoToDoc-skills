"""Task 10: ASR + 截图并行化测试。"""
from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

from videotodoc.config import Settings
from videotodoc.models import Section, Slide, SlideSet, Transcript, TranscriptSegment


def _make_test_image(path: Path, color: tuple = (255, 255, 255)) -> None:
    from PIL import Image
    img = Image.new("RGB", (100, 100), color=color)
    img.save(path)


class TestPipelineParallel:
    def test_capture_video_parallel_asr_detect(self, tmp_path):
        """capture_video 中 transcribe_audio 和 detect_slides 应并行执行。"""
        from videotodoc.pipeline import capture_video

        video_path = tmp_path / "test.mp4"
        video_path.write_bytes(b"fake video")
        runs_dir = tmp_path / "runs"

        settings = Settings(
            asr_backend="mock",
            asr_model="mock",
            capture_mode="fast",
            scene_threshold=0.4,
            hash_threshold=8,
        )

        delay_per_task = 0.2

        def mock_extract_audio(vp, ap, settings, force=False):
            ap.parent.mkdir(parents=True, exist_ok=True)
            ap.write_bytes(b"audio")
            return ap

        def mock_probe(vp):
            return 30000

        def mock_capture_interval(duration):
            return 10

        def mock_transcribe(audio, tp, settings, force=False):
            time.sleep(delay_per_task)
            return Transcript(backend="mock", language="zh", segments=[
                TranscriptSegment(start_ms=0, end_ms=15000, text="第一段"),
                TranscriptSegment(start_ms=15000, end_ms=30000, text="第二段"),
            ])

        def mock_detect(vp, od, oj, settings, force=False, skip_dedupe=False):
            time.sleep(delay_per_task)
            return SlideSet(slides=[])

        def mock_generate_pending(candidates, transcript, dur, **kw):
            return {"segments": []}

        with patch("videotodoc.pipeline.extract_audio", side_effect=mock_extract_audio), \
             patch("videotodoc.pipeline.probe_duration_ms", side_effect=mock_probe), \
             patch("videotodoc.pipeline.capture_interval_for_duration", side_effect=mock_capture_interval), \
             patch("videotodoc.pipeline.transcribe_audio", side_effect=mock_transcribe), \
             patch("videotodoc.pipeline.detect_slides", side_effect=mock_detect), \
             patch("videotodoc.pipeline.generate_pending_segments", side_effect=mock_generate_pending):

            start = time.time()
            result = capture_video(video_path, runs_dir, settings, force_rebuild={"all"})
            elapsed = time.time() - start

        serial_time = delay_per_task * 2
        assert elapsed < serial_time * 0.75, (
            f"ASR 与 detect_slides 应并行执行（串行≈{serial_time:.2f}s，实际={elapsed:.2f}s）"
        )

    def test_process_video_parallel_asr_detect(self, tmp_path):
        """process_video 中 transcribe_audio 和 detect_slides 并行，文档生成正常。"""
        from videotodoc.pipeline import process_video

        video_path = tmp_path / "test.mp4"
        video_path.write_bytes(b"fake video")
        runs_dir = tmp_path / "runs"

        settings = Settings(
            asr_backend="mock",
            asr_model="mock",
            capture_mode="fast",
            scene_threshold=0.4,
            hash_threshold=8,
        )

        delay = 0.15

        def mock_extract_audio(vp, ap, settings, force=False):
            ap.parent.mkdir(parents=True, exist_ok=True)
            ap.write_bytes(b"audio")
            return ap

        def mock_transcribe(audio, tp, settings, force=False):
            time.sleep(delay)
            return Transcript(backend="mock", language="zh", segments=[
                TranscriptSegment(start_ms=0, end_ms=10000, text="测试文字"),
            ])

        def _fresh_slides(tag: str) -> SlideSet:
            img_path = tmp_path / f"mock_slide_{tag}.png"
            _make_test_image(img_path, (128, 128, 128))
            return SlideSet(slides=[
                Slide(slide_index=1, image_path=str(img_path), start_ms=0, end_ms=10000,
                      capture_ms=8000, confidence=0.9, hash="0000000000000001", edge_density=0.2),
            ])

        def mock_detect(vp, od, oj, settings, force=False, skip_dedupe=False):
            time.sleep(delay)
            return _fresh_slides("detect")

        def mock_trim(candidates, transcript, vp, td, settings):
            return _fresh_slides("trim")

        def mock_dedupe(candidates, settings):
            return _fresh_slides("dedupe")

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
            return [Section(slide_index=1, image_path="", start_ms=0, end_ms=10000, capture_ms=8000, transcript="测试内容", segment_indexes=[0])]

        def mock_gen_mindmap(title, sections, path, settings):
            path.write_text("mindmap", encoding="utf-8")
            return "mm"

        def mock_render_mindmap(rd, mindmap_path=None, image_path=None):
            if image_path:
                _make_test_image(image_path, (200, 200, 200))

        def mock_render_orig(title, sections, path):
            path.write_text("# orig", encoding="utf-8")

        def mock_render_compact(title, sections, path, mm=None):
            path.write_text("# compact", encoding="utf-8")

        def mock_ensure_semantic(title, sections, path, mm=None):
            path.write_text("# semantic", encoding="utf-8")

        def mock_md2docx(md, docx):
            docx.write_bytes(b"docx")
            return docx

        def mock_quality(path, transcript, slides, sections, offset):
            path.write_text("# quality", encoding="utf-8")

        with patch("videotodoc.pipeline.extract_audio", side_effect=mock_extract_audio), \
             patch("videotodoc.pipeline.transcribe_audio", side_effect=mock_transcribe), \
             patch("videotodoc.pipeline.detect_slides", side_effect=mock_detect), \
             patch("videotodoc.pipeline.trim_candidates_by_transcript", side_effect=mock_trim), \
             patch("videotodoc.pipeline.deduplicate_slides", side_effect=mock_dedupe), \
             patch("videotodoc.pipeline.materialize_selected_slides", side_effect=mock_materialize), \
             patch("videotodoc.pipeline.estimate_sync_offset_ms", side_effect=mock_estimate), \
             patch("videotodoc.pipeline.align_sections", side_effect=mock_align), \
             patch("videotodoc.pipeline.generate_mindmap", side_effect=mock_gen_mindmap), \
             patch("videotodoc.pipeline.render_mindmap_and_refresh_docs", side_effect=mock_render_mindmap), \
             patch("videotodoc.pipeline.render_original_markdown", side_effect=mock_render_orig), \
             patch("videotodoc.pipeline.render_compact_markdown", side_effect=mock_render_compact), \
             patch("videotodoc.pipeline.ensure_semantic_markdown", side_effect=mock_ensure_semantic), \
             patch("videotodoc.pipeline.markdown_to_docx", side_effect=mock_md2docx), \
             patch("videotodoc.pipeline.write_quality_report", side_effect=mock_quality):

            start = time.time()
            result = process_video(video_path, runs_dir, settings, force_rebuild={"all"})
            elapsed = time.time() - start

        serial_asr_detect = delay * 2
        assert elapsed < serial_asr_detect + 3, (
            f"ASR/detect 并行后总耗时不应包含两者串行叠加"
        )
        assert result.markdown_path.exists()
