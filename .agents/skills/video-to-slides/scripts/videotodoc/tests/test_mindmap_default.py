from pathlib import Path
from unittest.mock import patch

from videotodoc.mindmap import render_mindmap_and_refresh_docs


def test_default_uses_python_renderer(tmp_path: Path):
    mmd = tmp_path / "mindmap.mmd"
    mmd.write_text("""mindmap\n  root((R))\n    A\n      a1\n""", encoding="utf-8")
    with patch("videotodoc.mindmap._render_mindmap_with_python") as mock_py, \
         patch("videotodoc.mindmap._run_mmdc") as mock_mmdc:
        render_mindmap_and_refresh_docs(tmp_path)
        assert mock_py.called
        assert not mock_mmdc.called
