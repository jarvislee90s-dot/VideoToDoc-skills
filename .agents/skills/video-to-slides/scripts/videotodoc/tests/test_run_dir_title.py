from pathlib import Path
from unittest.mock import MagicMock, patch

from videotodoc.config import Settings
from videotodoc.pipeline import process_video


def test_process_video_uses_run_dir_name_for_slug(tmp_path):
    """--run-dir 复用 video-summary 目录时，产物名应从 run_dir 名推断，而非 video.mp4。"""
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"fake")
    run_dir = tmp_path / "我的测试视频_20260628_120000"
    run_dir.mkdir()

    settings = Settings()

    def noop(*args, **kwargs):
        pass

    def fake_extract(*args, **kwargs):
        return args[1]

    def fake_transcribe(*args, **kwargs):
        from videotodoc.models import Transcript
        return Transcript(segments=[], backend="test", language="zh")

    def fake_detect(*args, **kwargs):
        from videotodoc.models import SlideSet
        return SlideSet(slides=[], metadata={})

    def fake_slideset(*args, **kwargs):
        from videotodoc.models import SlideSet
        return SlideSet(slides=[], metadata={})

    def fake_render_mindmap(*args, **kwargs):
        return [], []

    with patch("videotodoc.pipeline.extract_audio", side_effect=fake_extract), \
         patch("videotodoc.pipeline.transcribe_audio", side_effect=fake_transcribe), \
         patch("videotodoc.pipeline.detect_slides", side_effect=fake_detect), \
         patch("videotodoc.pipeline.estimate_sync_offset_ms", return_value=0), \
         patch("videotodoc.pipeline.align_sections", return_value=[]), \
         patch("videotodoc.pipeline.generate_mindmap", side_effect=noop), \
         patch("videotodoc.pipeline.render_mindmap_and_refresh_docs", side_effect=fake_render_mindmap), \
         patch("videotodoc.pipeline.render_original_markdown", side_effect=noop), \
         patch("videotodoc.pipeline.render_compact_markdown", side_effect=noop), \
         patch("videotodoc.pipeline.ensure_semantic_markdown", side_effect=noop), \
         patch("videotodoc.pipeline.markdown_to_docx", return_value=None), \
         patch("videotodoc.pipeline.write_quality_report", side_effect=noop), \
         patch("videotodoc.pipeline.trim_candidates_by_transcript", return_value=[]), \
         patch("videotodoc.pipeline.deduplicate_slides", side_effect=fake_slideset), \
         patch("videotodoc.pipeline.materialize_selected_slides", side_effect=fake_slideset), \
         patch("videotodoc.pipeline.write_json", side_effect=noop), \
         patch("videotodoc.pipeline.read_json", return_value={}), \
         patch("videotodoc.pipeline._transcript_from_external") as mock_transcript:
        from videotodoc.models import Transcript
        mock_transcript.return_value = Transcript(segments=[], backend="test", language="zh")
        result = process_video(video_path, tmp_path, settings, run_dir=run_dir)

    assert "我的测试视频" in result.markdown_path.name
    assert "video_讲义" not in result.markdown_path.name
    assert "我的测试视频" in result.semantic_markdown_path.name
    assert "我的测试视频" in result.mindmap_path.name
