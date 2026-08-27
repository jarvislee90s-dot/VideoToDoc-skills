#!/usr/bin/env python3
"""video-to-slides 阶段 3 收尾 wrapper。

统一执行图片恢复 + 思维导图渲染 + Word 生成。
Agent 不需要分别跑 restore_images.py 和 render_mindmap.py，只跑本脚本即可。

用法：
    python3 finalize.py <run_dir>
"""
from __future__ import annotations

import subprocess
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

# finalize.py 与 restore_images.py / render_mindmap.py 同处 scripts/ 目录
_SCRIPTS_DIR = Path(__file__).resolve().parent


def find_compact_and_semantic(run_dir: Path) -> tuple[Path, Path]:
    """在 run_dir 下找紧凑版和整理版 Markdown。"""
    compact_candidates = sorted(run_dir.glob("*_讲义_紧凑版_*.md"))
    semantic_candidates = sorted(run_dir.glob("*_讲义_整理版_*.md"))
    if not compact_candidates:
        raise FileNotFoundError(f"run_dir 下找不到紧凑版：{run_dir}")
    if not semantic_candidates:
        raise FileNotFoundError(f"run_dir 下找不到整理版：{run_dir}")
    return compact_candidates[0], semantic_candidates[0]


def run_restore_images(compact_md: Path, semantic_md: Path) -> None:
    """调 restore_images.py 恢复图片（不再同步目录）。"""
    script = _SCRIPTS_DIR / "restore_images.py"
    # 用当前解释器调用，避免 python3 指向与依赖不匹配的解释器
    subprocess.run(
        [sys.executable, str(script), str(compact_md), str(semantic_md)],
        check=True,
    )


def run_render_mindmap(run_dir: Path) -> None:
    """调 render_mindmap.py 渲染思维导图 + 生成/刷新两份 Word。"""
    script = _SCRIPTS_DIR / "render_mindmap.py"
    subprocess.run(
        [sys.executable, str(script), str(run_dir)],
        check=True,
    )


def main(argv: list[str] | None = None) -> int:
    # argv 显式传入时用之（便于测试），否则读命令行
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print("用法：python3 finalize.py <run_dir>", file=sys.stderr)
        return 1
    run_dir = Path(args[0]).expanduser().resolve()
    if not run_dir.is_dir():
        print(f"❌ run_dir 不存在：{run_dir}", file=sys.stderr)
        return 2

    compact_md, semantic_md = find_compact_and_semantic(run_dir)
    print(f"▶ 恢复图片：{compact_md.name} → {semantic_md.name}", flush=True)
    run_restore_images(compact_md, semantic_md)
    print("▶ 渲染思维导图 + 生成 Word", flush=True)
    run_render_mindmap(run_dir)
    print(f"✅ 收尾完成：{run_dir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
