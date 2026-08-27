from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from PIL import Image

from .document import ensure_mindmap_link, markdown_to_docx
from .mindmap_mermaid import add_chapter_numbers, inject_tidy_tree_config
from .utils import VideoToDocError


def _find_mindmap_source(run_dir: Path) -> Path:
    """查找思维导图源文件。

    优先匹配 SKILL.md 约定的 <标题>_思维导图_<时间戳>.mmd（取最新），
    fallback 到旧版 mindmap.mmd（向后兼容）。两者都没有时报错。
    """
    for pattern in ("*_思维导图_*.mmd", "mindmap.mmd"):
        candidates = sorted(run_dir.glob(pattern), reverse=True)
        if candidates:
            return candidates[0]
    raise VideoToDocError(
        f"在 {run_dir} 找不到思维导图源文件"
        "（*_思维导图_*.mmd 或 mindmap.mmd）。"
        "请先完成 Agent 整理步骤并编写思维导图源文件，再运行此脚本。"
    )


def render_mindmap_and_refresh_docs(
    run_dir: Path,
    mindmap_path: Path | None = None,
    image_path: Path | None = None,
    use_mermaid: bool = False,
) -> tuple[list[Path], list[Path]]:
    """使用 Mermaid tidy-tree 渲染思维导图，并生成/刷新所有 Markdown/Word 文档。"""
    del use_mermaid  # 已废弃，保留参数兼容性

    run_dir = run_dir.resolve()
    mindmap_path = mindmap_path or _find_mindmap_source(run_dir)
    image_path = image_path or (run_dir / "mindmap.png")
    if not mindmap_path.exists():
        raise VideoToDocError(f"找不到 Mermaid 源文件：{mindmap_path}")

    raw_text = mindmap_path.read_text(encoding="utf-8")
    numbered = add_chapter_numbers(raw_text)
    prepared = inject_tidy_tree_config(numbered)

    prepared_path = run_dir / "mindmap_prepared.mmd"
    prepared_path.write_text(prepared, encoding="utf-8")

    mmdc = _find_mmdc()
    _run_mmdc([mmdc, "-i", str(prepared_path), "-o", str(image_path), "-b", "transparent", "-w", "2400"])
    _verify_png_size(image_path)

    image_paths = [image_path]

    refreshed: list[Path] = []
    md_files = [p for p in run_dir.glob("*.md") if "质量报告" not in p.name]

    # 按目标 docx 分组；原始版与紧凑版会映射到同一 docx，优先采用紧凑版
    grouped: dict[Path, list[Path]] = {}
    for md_file in md_files:
        grouped.setdefault(_docx_path_for_markdown(md_file), []).append(md_file)

    for docx_file, sources in grouped.items():
        # 若同时存在紧凑版和其他版本，优先用紧凑版生成 docx
        preferred = next(
            (p for p in sources if "_讲义_紧凑版_" in p.stem),
            sources[0],
        )
        for md_file in sources:
            ensure_mindmap_link(md_file, image_paths)
        generated = markdown_to_docx(preferred, docx_file)
        if generated:
            refreshed.append(generated)

    return image_paths, refreshed


def _docx_path_for_markdown(md_path: Path) -> Path:
    """保持旧命名约定：紧凑版 Markdown 对应 _讲义_.docx，整理版保持同名。"""
    name = md_path.stem
    if "_讲义_紧凑版_" in name:
        slug, ts = name.split("_讲义_紧凑版_", 1)
        return md_path.with_name(f"{slug}_讲义_{ts}.docx")
    return md_path.with_suffix(".docx")


def _verify_png_size(png_path: Path, max_size: int = 8000) -> None:
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
        "找不到 mmdc。请先安装 Mermaid CLI（需 >= 11.4.0，该版本起才内置 tidy-tree 鱼骨布局插件）："
        'npm install -g "@mermaid-js/mermaid-cli@>=11.4.0"，'
        "或在项目内安装：npm install --prefix .tools/mermaid-cli \"@mermaid-js/mermaid-cli@>=11.4.0\""
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
