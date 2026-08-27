#!/usr/bin/env python3
"""渲染 run 目录中的 mindmap.mmd，并生成/刷新两份 Word 产物。"""

from __future__ import annotations

import argparse
import os
import sys
import subprocess
from pathlib import Path

from _project import find_project_dir, project_python

# Windows 控制台默认 GBK，脚本含 emoji 输出，强制 UTF-8 避免 UnicodeEncodeError
if sys.platform == "win32":
    for _s in (sys.stdout, sys.stderr):
        if _s and hasattr(_s, "reconfigure"):
            try:
                _s.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description="渲染思维导图并生成/刷新 Word 产物。")
    parser.add_argument("run_dir", nargs="?", type=Path, help="包含 mindmap.mmd 的 run 目录；不传则使用最新 run")
    parser.add_argument("--project-dir", type=Path, default=None)
    args = parser.parse_args()

    project_dir = find_project_dir(args.project_dir, args.run_dir.resolve() if args.run_dir else None)
    run_dir = args.run_dir.expanduser().resolve() if args.run_dir else _latest_run_dir(project_dir)
    if run_dir is None:
        print("未找到包含 mindmap.mmd 的 run 目录。请确认 Agent 已编写 mindmap.mmd。")
        return 2

    cmd = [str(project_python(project_dir)), "-m", "videotodoc.cli", "render-mindmap", str(run_dir)]
    result = subprocess.run(
        cmd, cwd=project_dir,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parent)},
        text=True, stdout=sys.stdout, stderr=sys.stderr,
    )
    return result.returncode


def _latest_run_dir(project_dir: Path) -> Path | None:
    runs_dir = project_dir / "runs"
    if not runs_dir.exists():
        return None
    candidates = []
    for p in runs_dir.iterdir():
        if not p.is_dir():
            continue
        # 任一命名约定存在即可（带时间戳的优先，mindmap.mmd 兼容）
        if (p / "mindmap.mmd").exists() or list(p.glob("*_思维导图_*.mmd")):
            candidates.append(p)
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime_ns)


if __name__ == "__main__":
    raise SystemExit(main())
