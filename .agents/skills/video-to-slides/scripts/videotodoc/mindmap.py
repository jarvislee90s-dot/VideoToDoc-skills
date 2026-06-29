from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from .document import ensure_mindmap_link, markdown_to_docx
from .utils import VideoToDocError

if TYPE_CHECKING:
    from PIL import ImageDraw
    from .mindmap_layout import LayoutConfig, LayoutNode, MindmapLayout


def render_mindmap_and_refresh_docs(run_dir: Path, mindmap_path: Path | None = None, image_path: Path | None = None) -> tuple[Path, list[Path]]:
    run_dir = run_dir.resolve()
    mindmap_path = mindmap_path or (run_dir / "mindmap.mmd")
    image_path = image_path or (run_dir / "mindmap.png")
    if not mindmap_path.exists():
        raise VideoToDocError(f"找不到 Mermaid 源文件：{mindmap_path}")

    mmdc = _find_mmdc()
    try:
        _run_mmdc([mmdc, "-i", str(mindmap_path), "-o", str(image_path), "-b", "transparent"])
    except VideoToDocError:
        _render_mindmap_with_python(mindmap_path, image_path)

    refreshed: list[Path] = []
    # 刷新所有 Markdown 和对应的 Word 文件
    for md_file in run_dir.glob("*.md"):
        if "质量报告" in md_file.name:
            continue
        ensure_mindmap_link(md_file, image_path)
        docx_file = md_file.with_suffix(".docx")
        if docx_file.exists():
            generated = markdown_to_docx(md_file, docx_file)
            if generated:
                refreshed.append(generated)
    return image_path, refreshed


def _find_mmdc() -> str:
    found = shutil.which("mmdc")
    if found:
        return found
    user_tools = Path.home() / ".tools" / "bin" / "mmdc"
    if user_tools.exists():
        return str(user_tools)
    local = Path("node_modules/.bin/mmdc")
    if local.exists():
        return str(local)
    bundled = Path(".tools/mermaid-cli/node_modules/.bin/mmdc")
    if bundled.exists():
        return str(bundled)
    raise VideoToDocError(
        "找不到 mmdc。请先安装 Mermaid CLI：npm install -g @mermaid-js/mermaid-cli，"
        "或在项目内安装：npm install --prefix .tools/mermaid-cli @mermaid-js/mermaid-cli"
    )


def _run_mmdc(args: list[str]) -> None:
    env = _mmdc_env()
    try:
        subprocess.run(
            args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, env=env, timeout=120,
        )
    except FileNotFoundError as exc:
        raise VideoToDocError(f"找不到命令：{args[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        cmd_str = " ".join(args)
        details = ""
        if exc.stderr:
            stderr_text = exc.stderr if isinstance(exc.stderr, str) else exc.stderr.decode("utf-8", errors="replace")
            if stderr_text.strip():
                details = f"\nstderr: {stderr_text.strip()}"
        elif exc.stdout:
            stdout_text = exc.stdout if isinstance(exc.stdout, str) else exc.stdout.decode("utf-8", errors="replace")
            if stdout_text.strip():
                details = f"\nstdout: {stdout_text.strip()}"
        raise VideoToDocError(f"命令执行超时（120s）：{cmd_str}{details}") from exc
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or exc.stdout.strip()
        raise VideoToDocError(f"命令执行失败：{' '.join(args)}\n{message}") from exc


def _mmdc_env() -> dict[str, str]:
    import os

    env = dict(os.environ)
    if "PUPPETEER_EXECUTABLE_PATH" not in env:
        chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        chromium = Path("/Applications/Chromium.app/Contents/MacOS/Chromium")
        if chrome.exists():
            env["PUPPETEER_EXECUTABLE_PATH"] = str(chrome)
        elif chromium.exists():
            env["PUPPETEER_EXECUTABLE_PATH"] = str(chromium)
    return env


def _render_mindmap_with_python(mindmap_path: Path, image_path: Path) -> None:
    try:
        from PIL import Image, ImageDraw, ImageFont  # type: ignore
    except ModuleNotFoundError as exc:
        raise VideoToDocError("mmdc 渲染失败，且未安装 Pillow，无法使用 Python fallback。") from exc

    root = _parse_mermaid_tree(mindmap_path.read_text(encoding="utf-8"))
    if not root:
        raise VideoToDocError(f"mindmap.mmd 没有可渲染节点：{mindmap_path}")

    _render_mindmap_with_python_from_tree(root, image_path)


def _render_mindmap_with_python_from_tree(root: _MindmapNode, image_path: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont  # type: ignore
    from .mindmap_layout import LayoutConfig, MindmapLayout, compute_layout

    cfg = LayoutConfig()
    layout = compute_layout(root, cfg)
    img = Image.new("RGB", (int(layout.image_width), int(layout.image_height)), "white")
    draw = ImageDraw.Draw(img)
    font_root = _load_font(14)
    font_chapter = _load_font(12)
    font_leaf = _load_font(10)
    _draw_layout_node(draw, layout.root_node, font_root, font_chapter, font_leaf)
    image_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(image_path)


def _draw_layout_node(draw: ImageDraw.ImageDraw, node: LayoutNode, font_root, font_chapter, font_leaf) -> None:
    x, y, w, h = node["x"], node["y"], node["width"], node["height"]
    level = node["level"]
    if level == 0:
        fill, outline, font, color = "#4caf50", "#4caf50", font_root, "white"
        radius = 10
    elif level == 1:
        fill, outline, font, color = "#dbeafe", "#1c60af", font_chapter, "#1f2937"
        radius = 8
    else:
        fill, outline, font, color = "#f8fafc", "#cbd5e1", font_leaf, "#1f2937"
        radius = 5

    draw.rounded_rectangle([x, y, x + w, y + h], radius=radius, fill=fill, outline=outline, width=2 if level <= 1 else 1)
    text = _wrap_text(node["text"], 12 if level == 0 else (10 if level == 1 else 9))
    bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=2)
    text_h = bbox[3] - bbox[1]
    draw.multiline_text((x + w / 2, y + h / 2 - text_h / 2), text, fill=color, font=font, spacing=2, anchor="mm")

    for child in node["children"]:
        _draw_connection(draw, node, child)
        _draw_layout_node(draw, child, font_root, font_chapter, font_leaf)


def _draw_connection(draw: ImageDraw.ImageDraw, parent: LayoutNode, child: LayoutNode) -> None:
    px = parent["x"] + parent["width"]
    py = parent["y"] + parent["height"] / 2
    cx = child["x"]
    cy = child["y"] + child["height"] / 2
    mid_x = (px + cx) / 2
    draw.line([(px, py), (mid_x, py), (mid_x, cy), (cx, cy)], fill="#aac2e6", width=2, joint="curve")


class _MindmapNode:
    def __init__(self, text: str, level: int) -> None:
        self.text = text
        self.level = level
        self.children: list[_MindmapNode] = []
        self.x = 0
        self.y = 0


def _parse_mermaid_mindmap(text: str) -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.strip() == "mindmap":
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        level = max(0, indent // 2 - 1)
        label = raw_line.strip()
        if label.startswith("root((") and label.endswith("))"):
            label = label[6:-2]
        label = label.strip().strip('"').strip("'")
        if label:
            result.append((level, label))
    return result


def _parse_mermaid_tree(text: str) -> _MindmapNode | None:
    parsed = _parse_mermaid_mindmap(text)
    if not parsed:
        return None
    root = _MindmapNode(parsed[0][1], parsed[0][0])
    stack: list[_MindmapNode] = [root]
    for level, label in parsed[1:]:
        node = _MindmapNode(label, level)
        while len(stack) > level:
            stack.pop()
        parent = stack[level - 1] if level > 0 and len(stack) >= level else root
        parent.children.append(node)
        if len(stack) > level:
            stack[level] = node
        else:
            stack.append(node)
    return root


def _load_font(size: int):
    from PIL import ImageFont  # type: ignore

    for path in (
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
    ):
        candidate = Path(path)
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def _wrap_text(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    lines = [text[index : index + width] for index in range(0, min(len(text), width * 2), width)]
    if len(text) > width * 2 and lines:
        lines[-1] = lines[-1][:-1] + "…"
    return "\n".join(lines)
