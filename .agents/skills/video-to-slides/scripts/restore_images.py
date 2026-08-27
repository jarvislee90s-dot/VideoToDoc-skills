#!/usr/bin/env python3
"""修复 Agent 语义整理后可能丢失的图片占位符。

用法：
    python3 restore_images.py <compact_md> <semantic_md>

从紧凑版提取图片路径，替换整理版中的 <!-- IMAGE:N --> 占位符。
目录由 Agent 在 ⑤ 步写入紧凑版、⑥ 步复制到整理版，本脚本不再同步目录。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Windows 控制台默认 GBK，脚本含 emoji 输出，强制 UTF-8 避免 UnicodeEncodeError
if sys.platform == "win32":
    for _s in (sys.stdout, sys.stderr):
        if _s and hasattr(_s, "reconfigure"):
            try:
                _s.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def extract_images_from_compact(compact_path: Path) -> dict[int, list[str]]:
    """从紧凑版提取每页的所有图片路径（按时间顺序）。"""
    text = compact_path.read_text(encoding="utf-8")
    images: dict[int, list[str]] = {}
    # 匹配 ### 第 N 页 后面紧跟的连续图片行
    page_pattern = re.compile(
        r"### 第 (\d+) 页.*?\n\n((?:!\[.*?\]\(.+?\)\n)+)",
        re.DOTALL,
    )
    for match in page_pattern.finditer(text):
        slide_index = int(match.group(1))
        image_block = match.group(2)
        image_paths = re.findall(r"!\[.*?\]\((.+?)\)", image_block)
        images[slide_index] = image_paths
    return images


def restore_images(compact_path: Path, semantic_path: Path) -> Path:
    """用紧凑版的图片路径替换整理版中的占位符。

    支持新旧两种占位符：
    - 新格式：<!-- IMAGE:N-M[:main] -->（N=页码，M=段内序号）
    - 旧格式：<!-- IMAGE:N -->（单图，兼容）
    """
    if not semantic_path.exists():
        raise FileNotFoundError(f"整理版不存在：{semantic_path}")
    if not compact_path.exists():
        raise FileNotFoundError(f"紧凑版不存在：{compact_path}")

    images = extract_images_from_compact(compact_path)
    if not images:
        print("⚠️  未从紧凑版提取到图片，跳过修复。", file=sys.stderr)
        return semantic_path

    text = semantic_path.read_text(encoding="utf-8")
    original = text

    # 替换新格式占位符 <!-- IMAGE:N-M[:main] -->
    new_placeholder = re.compile(r"<!-- IMAGE:(\d+)-(\d+)(?::main)? -->")

    def _replace_new(match: re.Match) -> str:
        slide_index = int(match.group(1))
        intra_idx = int(match.group(2))
        paths = images.get(slide_index, [])
        if 0 < intra_idx <= len(paths):
            return f"![第 {slide_index} 页]({paths[intra_idx - 1]})"
        return match.group(0)

    text = new_placeholder.sub(_replace_new, text)

    # 兼容旧格式 <!-- IMAGE:N -->（单图，取第一张）
    for slide_index, paths in images.items():
        if not paths:
            continue
        placeholder = f"<!-- IMAGE:{slide_index} -->"
        image_line = f"![第 {slide_index} 页]({paths[0]})"
        if placeholder in text:
            text = text.replace(placeholder, image_line)
            print(f"  ✅ 恢复第 {slide_index} 页图片")
        else:
            # 占位符已被删除时尝试在页码后插入
            page_header = f"### 第 {slide_index} 页"
            if page_header in text and image_line not in text:
                pattern = re.compile(
                    rf"({re.escape(page_header)}.*?\n)\n",
                    re.DOTALL,
                )
                text = pattern.sub(rf"\1\n\n{image_line}\n\n", text, count=1)
                print(f"  ✅ 插入第 {slide_index} 页图片")

    if text != original:
        semantic_path.write_text(text, encoding="utf-8")
        print(f"  📝 已更新：{semantic_path.name}")
    else:
        print(f"  ✅ 无需修复：{semantic_path.name}")

    return semantic_path


def main() -> int:
    args = sys.argv[1:]
    if len(args) < 2:
        print("用法：python3 restore_images.py <compact_md> <semantic_md>", file=sys.stderr)
        return 1

    compact_path = Path(args[0]).expanduser().resolve()
    semantic_path = Path(args[1]).expanduser().resolve()

    try:
        restore_images(compact_path, semantic_path)
        return 0
    except FileNotFoundError as e:
        print(f"❌ 错误：{e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
