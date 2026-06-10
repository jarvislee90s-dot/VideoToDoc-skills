#!/usr/bin/env python3
"""双击或命令行运行：渲染最新 run 的 mindmap.mmd 并刷新 Word。"""

from __future__ import annotations

import os
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
VENV_PYTHON = PROJECT_DIR / ".venv" / "bin" / "python"


def main() -> int:
    _reexec_with_venv()
    sys.path.insert(0, str(PROJECT_DIR / "src"))
    from videotodoc.cli import main as cli_main

    run_dir = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else _latest_run_dir()
    if not run_dir:
        print("未找到包含 mindmap.mmd 的 runs 目录。")
        return 2
    return cli_main(["render-mindmap", str(run_dir)])


def _reexec_with_venv() -> None:
    if not VENV_PYTHON.exists():
        return
    if Path(sys.executable).resolve() == VENV_PYTHON.resolve():
        return
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), __file__, *sys.argv[1:]])


def _latest_run_dir() -> Path | None:
    runs_dir = PROJECT_DIR / "runs"
    if not runs_dir.exists():
        return None
    candidates = [path for path in runs_dir.iterdir() if (path / "mindmap.mmd").exists()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: (path / "mindmap.mmd").stat().st_mtime_ns)


if __name__ == "__main__":
    raise SystemExit(main())
