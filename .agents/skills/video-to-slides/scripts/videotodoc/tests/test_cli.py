"""videotodoc.cli 模块的单元测试。"""
from pathlib import Path
from unittest.mock import MagicMock, patch

from videotodoc.cli import _process
from videotodoc.models import ProcessResult


def test_process_output_skips_missing_optional_fields(tmp_path: Path, capsys):
    """当可选输出字段为 None 时，_process 不应打印对应行。"""
    result = ProcessResult(
        run_dir=tmp_path,
        transcript_path=tmp_path / "t.json",
        slides_path=tmp_path / "s.json",
        sections_path=tmp_path / "a.json",
        markdown_path=tmp_path / "m.md",
        mindmap_path=None,
        compact_markdown_path=tmp_path / "c.md",
        semantic_markdown_path=tmp_path / "z.md",
        mindmap_image_path=None,
        mindmap_image_paths=[],
        docx_path=None,
        semantic_docx_path=None,
        quality_report_path=tmp_path / "q.md",
    )
    args = MagicMock()
    args.video = tmp_path / "video.mp4"
    args.runs_dir = tmp_path / "runs"
    args.run_dir = None
    args.force_rebuild = []
    args.config = None

    settings = MagicMock()
    settings.transcript_path = None

    with patch("videotodoc.cli._settings_from_args", return_value=settings):
        with patch("videotodoc.cli.process_video", return_value=result):
            rc = _process(args)

    captured = capsys.readouterr()
    assert rc == 0
    assert "- mindmap:" not in captured.out
    assert "- mindmap_image:" not in captured.out
    assert "- docx:" not in captured.out
    assert "- semantic_docx:" not in captured.out
    assert "- compact_markdown:" in captured.out
    assert "- semantic_markdown:" in captured.out


class TestVideoTypeArg:
    def test_video_type_passed_to_settings(self):
        from videotodoc.config import Settings
        s = Settings(video_type="talking_head")
        assert s.video_type == "talking_head"

    def test_video_type_default_auto(self):
        from videotodoc.config import Settings
        assert Settings().video_type == "auto"
