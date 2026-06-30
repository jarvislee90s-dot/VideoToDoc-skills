from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from PIL import Image

from .document import ensure_mindmap_link, markdown_to_docx
from .mindmap_mermaid import add_chapter_numbers, inject_tidy_tree_config, split_mmd_by_chapters
from .utils import VideoToDocError


def render_mindmap_and_refresh_docs(
    run_dir: Path,
    mindmap_path: Path | None = None,
    image_path: Path | None = None,
    use_mermaid: bool = False,
) -> tuple[list[Path], list[Path]]:
    """使用 Mermaid tidy-tree 渲染思维导图，并刷新所有 Markdown/Word 文档。"""
    del use_mermaid  # 已废弃，保留参数兼容性

    run_dir = run_dir.resolve()
    mindmap_path = mindmap_path or (run_dir / "mindmap.mmd")
    image_path = image_path or (run_dir / "mindmap.png")
    if not mindmap_path.exists():
        raise VideoToDocError(f"找不到 Mermaid 源文件：{mindmap_path}")

    raw_text = mindmap_path.read_text(encoding="utf-8")
    numbered = add_chapter_numbers(raw_text)
    sub_mmds = split_mmd_by_chapters(numbered)

    image_paths: list[Path] = []
    stem = image_path.stem
    suffix = image_path.suffix
    parent = image_path.parent
    mmdc = _find_mmdc()

    for index, sub_mmd in enumerate(sub_mmds, start=1):
        prepared = inject_tidy_tree_config(sub_mmd)
        sub_path = parent / f"{stem}_{index:02d}.mmd"
        png_path = parent / f"{stem}_{index:02d}{suffix}"
        sub_path.write_text(prepared, encoding="utf-8")
        _run_mmdc([mmdc, "-i", str(sub_path), "-o", str(png_path), "-b", "transparent", "-w", "2400"])
        _verify_png_size(png_path)
        image_paths.append(png_path)

    refreshed: list[Path] = []
    for md_file in run_dir.glob("*.md"):
        if "质量报告" in md_file.name:
            continue
        ensure_mindmap_link(md_file, image_paths)
        docx_file = md_file.with_suffix(".docx")
        if docx_file.exists():
            generated = markdown_to_docx(md_file, docx_file)
            if generated:
                refreshed.append(generated)
    return image_paths, refreshed


def _verify_png_size(png_path: Path, max_size: int = 3000) -> None:
    with Image.open(png_path) as img:
        if img.width > max_size or img.height > max_size:
            raise VideoToDocError(
                f"思维导图尺寸过大：{img.width}x{img.height}px，超过 {max_size}px"
            )


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
