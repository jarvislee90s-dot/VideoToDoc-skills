from pathlib import Path
from unittest.mock import MagicMock, patch

from videotodoc.config import Settings
from videotodoc.pipeline import process_video


def test_process_video_uses_run_dir_title_without_slugify(tmp_path):
    """--run-dir 复用 video-summary 目录时，产物名和 Markdown 标题应使用 run_dir 原始标题，不做 slugify。"""
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"fake")
    original_title = "内存暴涨，谁在哭？谁在笑？"
    run_dir = tmp_path / f"{original_title}_20260628_120000"
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

    with patch("videotodoc.pipeline.extract_audio", side_effect=fake_extract), \
         patch("videotodoc.pipeline.transcribe_audio", side_effect=fake_transcribe), \
         patch("videotodoc.pipeline.detect_slides", side_effect=fake_detect), \
         patch("videotodoc.pipeline.estimate_sync_offset_ms", return_value=0), \
         patch("videotodoc.pipeline.align_sections", return_value=[]), \
         patch("videotodoc.pipeline.render_original_markdown") as mock_render_orig, \
         patch("videotodoc.pipeline.render_compact_markdown") as mock_render_compact, \
         patch("videotodoc.pipeline.ensure_semantic_markdown") as mock_render_semantic, \
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

    assert result.markdown_path.name.startswith(f"{original_title}_讲义_")
    assert "video_讲义" not in result.markdown_path.name
    assert result.semantic_markdown_path.name.startswith(f"{original_title}_讲义_整理版_")
    assert result.compact_markdown_path.name.startswith(f"{original_title}_讲义_紧凑版_")
    # 确保 Markdown 内部标题也使用原始标题，而非 slugified 版本
    assert mock_render_orig.call_args[0][0] == original_title
    assert mock_render_compact.call_args[0][0] == original_title
    assert mock_render_semantic.call_args[0][0] == original_title
    # 不应出现 slugified 版本（标点被替换为下划线）
    slugified_title = "内存暴涨_谁在哭_谁在笑"
    assert slugified_title not in result.markdown_path.name
    assert result.mindmap_path is None
    assert result.docx_path is None
    assert result.semantic_docx_path is None
