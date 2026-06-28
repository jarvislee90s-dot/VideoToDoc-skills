#!/usr/bin/env python3
"""修复 Agent 语义整理后可能丢失的图片占位符，并同步目录。

用法：
    python3 restore_images.py <compact_md> <semantic_md> [--no-sync-toc]

从紧凑版提取图片路径，替换整理版中的 <!-- IMAGE:N --> 占位符；
默认同时把紧凑版中 ## 图文讲义 与第一个 ### 第 N 页 之间的目录同步到整理版。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def extract_toc_from_compact(compact_path: Path) -> str | None:
    """从紧凑版提取目录（## 图文讲义 与第一个 ### 第 N 页 之间的内容）。"""
    text = compact_path.read_text(encoding="utf-8")
    match = re.search(
        r"## 图文讲义\n\n(.*?)\n\n### 第 \d+ 页",
        text,
        re.DOTALL,
    )
    if not match:
        return None
    toc = match.group(1).strip()
    # 如果目录为空或只是分隔线，视为无目录
    if not toc or toc == "---":
        return None
    return toc


def sync_toc(compact_path: Path, semantic_path: Path) -> bool:
    """把紧凑版的目录同步到整理版标题之后、第一个页码之前。"""
    toc = extract_toc_from_compact(compact_path)
    if not toc:
        print("  ℹ️  紧凑版无目录，跳过同步。")
        return False

    # 去掉目录末尾可能存在的分隔线，避免整理版出现重复分隔线
    toc = re.sub(r"\n*---\s*$", "", toc).strip()

    text = semantic_path.read_text(encoding="utf-8")
    original = text

    # 在整理版中，找到 H1 标题后的第一个 ### 第 N 页
    # 把 H1 与该页之间的内容替换为目录（保留标题）
    pattern = re.compile(
        r"^(# .+?)\n\n.*?(?=### 第 \d+ 页)",
        re.DOTALL,
    )
    replacement = rf"\1\n\n{toc}\n\n---\n\n"
    text, count = pattern.subn(replacement, text, count=1)

    if count == 0:
        print("  ⚠️  未找到整理版的标题或页码，无法同步目录。", file=sys.stderr)
        return False

    if text != original:
        semantic_path.write_text(text, encoding="utf-8")
        print("  📝 已同步目录到整理版")
        return True
    print("  ✅ 整理版目录已一致")
    return False


def extract_images_from_compact(compact_path: Path) -> dict[int, str]:
    """从紧凑版提取每页的图片路径。"""
    text = compact_path.read_text(encoding="utf-8")
    images: dict[int, str] = {}
    # 匹配 ### 第 N 页 和下面的 ![第 N 页](path)
    page_pattern = re.compile(
        r"### 第 (\d+) 页.*?\n\n!\[.*?\]\((.+?)\)",
        re.DOTALL,
    )
    for match in page_pattern.finditer(text):
        slide_index = int(match.group(1))
        image_path = match.group(2)
        images[slide_index] = image_path
    return images


def restore_images(compact_path: Path, semantic_path: Path, sync_toc_enabled: bool = True) -> Path:
    """用紧凑版的图片路径替换整理版中的占位符，并可选同步目录。"""
    if not semantic_path.exists():
        raise FileNotFoundError(f"整理版不存在：{semantic_path}")
    if not compact_path.exists():
        raise FileNotFoundError(f"紧凑版不存在：{compact_path}")

    if sync_toc_enabled:
        sync_toc(compact_path, semantic_path)

    images = extract_images_from_compact(compact_path)
    if not images:
        print("⚠️  未从紧凑版提取到图片，跳过修复。", file=sys.stderr)
        return semantic_path

    text = semantic_path.read_text(encoding="utf-8")
    original = text

    # 替换 <!-- IMAGE:N --> 占位符为实际图片
    for slide_index, image_path in images.items():
        placeholder = f"<!-- IMAGE:{slide_index} -->"
        image_line = f"![第 {slide_index} 页]({image_path})"
        if placeholder in text:
            text = text.replace(placeholder, image_line)
            print(f"  ✅ 恢复第 {slide_index} 页图片")
        else:
            # 如果占位符已被删除，尝试在对应页码后插入图片
            page_header = f"### 第 {slide_index} 页"
            if page_header in text and image_line not in text:
                # 在页码行后插入图片
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
        print("用法：python3 restore_images.py <compact_md> <semantic_md> [--no-sync-toc]", file=sys.stderr)
        return 1

    compact_path = Path(args[0]).expanduser().resolve()
    semantic_path = Path(args[1]).expanduser().resolve()
    sync_toc_enabled = "--no-sync-toc" not in args

    try:
        restore_images(compact_path, semantic_path, sync_toc_enabled=sync_toc_enabled)
        return 0
    except FileNotFoundError as e:
        print(f"❌ 错误：{e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
