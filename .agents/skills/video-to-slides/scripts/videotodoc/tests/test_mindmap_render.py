import tempfile
from pathlib import Path
from PIL import Image

from videotodoc.mindmap import _render_mindmap_with_python_from_tree, _parse_mermaid_tree

SAMPLE = """mindmap
  root((Test))
    A
      a1
      a2
    B
      b1
"""

def test_render_creates_png():
    root = _parse_mermaid_tree(SAMPLE)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "mindmap.png"
        _render_mindmap_with_python_from_tree(root, out)
        assert out.exists()
        img = Image.open(out)
        assert img.format == "PNG"
        assert img.width > 0 and img.height > 0
