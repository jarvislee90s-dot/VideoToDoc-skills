from __future__ import annotations

import sys
from pathlib import Path

# 将共享模块目录加入搜索路径
_shared_dir = Path(__file__).resolve().parent.parent.parent / "_shared"
if str(_shared_dir) not in sys.path:
    sys.path.insert(0, str(_shared_dir))

from project import find_project_dir, project_python  # noqa: F401
