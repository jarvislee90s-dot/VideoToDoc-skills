#!/usr/bin/env python3
"""渲染 run 目录中的 mindmap.mmd，并刷新两份 Word。"""

from __future__ import annotations

import argparse
import os
import sys
import subprocess
from pathlib import Path

from _project import find_project_dir, project_python


def main() -> int:
    parser = argparse.ArgumentParser(description="渲染思维导图并刷新 Word 产物。")
    parser.add_argument("run_dir", nargs="?", type=Path, help="包含 mindmap.mmd 的 run 目录；不传则使用最新 run")
    parser.add_argument("--project-dir", type=Path, default=None)
    parser.add_argument("--mermaid", action="store_true", help="使用 Mermaid CLI 渲染（默认使用 Python 渲染器）")
    args = parser.parse_args()

    project_dir = find_project_dir(args.project_dir, args.run_dir.resolve() if args.run_dir else None)
    run_dir = args.run_dir.expanduser().resolve() if args.run_dir else _latest_run_dir(project_dir)
    if run_dir is None:
        print("未找到包含 mindmap.mmd 的 run 目录。")
        return 2

    cmd = [str(project_python(project_dir)), "-m", "videotodoc.cli", "render-mindmap", str(run_dir)]
    if args.mermaid:
        cmd.append("--mermaid")
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
    candidates = [p for p in runs_dir.iterdir() if (p / "mindmap.mmd").exists()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: (p / "mindmap.mmd").stat().st_mtime_ns)


if __name__ == "__main__":
    raise SystemExit(main())
