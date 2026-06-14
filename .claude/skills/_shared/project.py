from __future__ import annotations

import os
import sys
from pathlib import Path


def find_project_dir(explicit: str | Path | None = None, anchor: Path | None = None, allow_runs_only: bool = False) -> Path:
    """定位项目根目录。

    搜索顺序（优先级从高到低）：
    1. explicit 参数
    2. VIDEOTODOC_PROJECT_DIR 环境变量
    3. 当前目录（cwd）
    4. anchor 及其父目录
    5. 脚本所在目录及其父目录

    判断标准：存在 .claude/skills/video-to-slides/scripts/videotodoc/cli.py
    """
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    env_project = os.environ.get("VIDEOTODOC_PROJECT_DIR")
    if env_project:
        candidates.append(Path(env_project))
    candidates.append(Path.cwd())
    if anchor is not None:
        candidates.extend([anchor, *anchor.parents])
    candidates.extend(Path(__file__).resolve().parents)

    seen: set[Path] = set()
    for candidate in candidates:
        path = candidate.expanduser().resolve()
        if path in seen:
            continue
        seen.add(path)
        for root in (path, *path.parents):
            # 检查 .claude/skills 内嵌结构
            if (root / ".claude" / "skills" / "video-to-slides" / "scripts" / "videotodoc" / "cli.py").exists():
                return root
            if allow_runs_only and (root / "runs").is_dir() and not (root / ".claude").is_dir():
                return root
    raise SystemExit(
        "未找到项目根目录；"
        "请在项目内运行，或传入 --project-dir，或设置 VIDEOTODOC_PROJECT_DIR。"
    )


def project_python(project_dir: Path) -> Path:
    """优先使用项目 .venv 的 Python，否则使用当前解释器。"""
    venv_python = project_dir / ".venv" / "bin" / "python"
    if venv_python.exists():
        return venv_python
    return Path(sys.executable)
