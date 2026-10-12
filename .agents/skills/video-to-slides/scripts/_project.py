from __future__ import annotations

import sys
from pathlib import Path


def _find_shared_dir() -> Path:
    """定位 _shared/ 依赖目录，兼容两种安装形态：

    1. 打包形态（单技能包）：_shared/ 在 skill 目录内，与 scripts/ 同级
       <skills>/video-to-slides/{SKILL.md, _shared/, scripts/}
    2. 仓库形态：_shared/ 与各 skill 目录同级
       <repo>/.agents/skills/{_shared/, video-to-slides/, ...}
    """
    here = Path(__file__).resolve()  # <skill>/scripts/_project.py
    for candidate in (
        here.parent.parent / "_shared",
        here.parent.parent.parent / "_shared",
    ):
        if candidate.is_dir():
            return candidate
    return here.parent.parent / "_shared"


# 将共享模块目录加入搜索路径
_shared_dir = _find_shared_dir()
if str(_shared_dir) not in sys.path:
    sys.path.insert(0, str(_shared_dir))

from project import find_project_dir, project_python  # noqa: F401
