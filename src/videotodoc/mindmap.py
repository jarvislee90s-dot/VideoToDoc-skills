from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .document import ensure_mindmap_link, markdown_to_docx
from .utils import VideoToDocError


def render_mindmap_and_refresh_docs(run_dir: Path) -> tuple[Path, list[Path]]:
    run_dir = run_dir.resolve()
    mindmap_path = run_dir / "mindmap.mmd"
    image_path = run_dir / "mindmap.png"
    if not mindmap_path.exists():
        raise VideoToDocError(f"找不到 Mermaid 源文件：{mindmap_path}")

    mmdc = _find_mmdc()
    try:
        _run_mmdc([mmdc, "-i", str(mindmap_path), "-o", str(image_path), "-b", "transparent"])
    except VideoToDocError:
        _render_mindmap_with_python(mindmap_path, image_path)

    refreshed: list[Path] = []
    for markdown_name, docx_name in (
        ("draft_compact.md", "draft.docx"),
        ("draft_semantic.md", "draft_semantic.docx"),
    ):
        markdown_path = run_dir / markdown_name
        if not markdown_path.exists():
            continue
        ensure_mindmap_link(markdown_path, image_path)
        docx_path = run_dir / docx_name
        generated = markdown_to_docx(markdown_path, docx_path)
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
        subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, env=env)
    except FileNotFoundError as exc:
        raise VideoToDocError(f"找不到命令：{args[0]}") from exc
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

    font = _load_font(30)
    small_font = _load_font(24)
    margin_x = 90
    margin_y = 70
    level_gap = 410
    row_gap = 88
    box_h = 58
    leaf_count = _count_leaves(root)
    max_level = _max_level(root)
    width = margin_x * 2 + (max_level + 1) * level_gap + 280
    height = margin_y * 2 + leaf_count * row_gap
    image = Image.new("RGB", (max(width, 1500), max(height, 800)), "white")
    draw = ImageDraw.Draw(image)
    cursor = [0]
    _assign_positions(root, margin_x, margin_y, level_gap, row_gap, cursor)
    _draw_edges(draw, root)
    _draw_nodes(draw, root, font, small_font, box_h)

    image_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(image_path)


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


def _count_leaves(node: _MindmapNode) -> int:
    if not node.children:
        return 1
    return sum(_count_leaves(child) for child in node.children)


def _max_level(node: _MindmapNode) -> int:
    if not node.children:
        return node.level
    return max(_max_level(child) for child in node.children)


def _assign_positions(
    node: _MindmapNode,
    margin_x: int,
    margin_y: int,
    level_gap: int,
    row_gap: int,
    cursor: list[int],
) -> None:
    node.x = margin_x + node.level * level_gap
    if not node.children:
        node.y = margin_y + cursor[0] * row_gap
        cursor[0] += 1
        return
    for child in node.children:
        _assign_positions(child, margin_x, margin_y, level_gap, row_gap, cursor)
    node.y = sum(child.y for child in node.children) // len(node.children)


def _draw_edges(draw: object, node: _MindmapNode) -> None:
    parent_rect = _node_rect(node)
    for child in node.children:
        child_rect = _node_rect(child)
        draw.line(
            (
                parent_rect[2],
                (parent_rect[1] + parent_rect[3]) // 2,
                child_rect[0],
                (child_rect[1] + child_rect[3]) // 2,
            ),
            fill="#9cb8df",
            width=3,
        )
        _draw_edges(draw, child)


def _draw_nodes(draw: object, node: _MindmapNode, font: object, small_font: object, box_h: int) -> None:
    rect = _node_rect(node)
    fill = "#1c60af" if node.level == 0 else "#eef5ff"
    outline = "#1c60af" if node.level <= 1 else "#aac2e6"
    draw.rounded_rectangle(rect, radius=16, fill=fill, outline=outline, width=3)
    wrapped = _wrap_text(node.text, 13 if node.level == 0 else 15)
    text_font = font if node.level == 0 else small_font
    color = "white" if node.level == 0 else "#1f2937"
    draw.multiline_text((rect[0] + 18, rect[1] + 11), wrapped, fill=color, font=text_font, spacing=2)
    for child in node.children:
        _draw_nodes(draw, child, font, small_font, box_h)


def _node_rect(node: _MindmapNode) -> tuple[int, int, int, int]:
    box_w = 280 if node.level == 0 else 320
    box_h = 58
    return (node.x, node.y, node.x + box_w, node.y + box_h)


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
