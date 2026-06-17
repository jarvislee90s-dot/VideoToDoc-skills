from __future__ import annotations

import sys
from pathlib import Path

# 将共享模块目录加入搜索路径
_shared_dir = Path(__file__).resolve().parent.parent.parent / "_shared"
if str(_shared_dir) not in sys.path:
    sys.path.insert(0, str(_shared_dir))

from project import find_project_dir as _find, project_python  # noqa: F401


def find_project_dir(explicit=None, anchor=None):
    """飞书发布支持非 VideoToDoc 项目（仅有 runs/ 目录即可）。"""
    return _find(explicit, anchor, allow_runs_only=True)
