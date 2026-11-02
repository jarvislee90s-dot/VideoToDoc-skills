"""测试公共配置：将 video-summary 的 scripts 目录注入 sys.path。

pytest.ini 的 pythonpath 只包含 video-to-slides/scripts 与 _shared，
不含 video-summary/scripts，因此这里手动前置插入，
保证 `import process` / `from sources import ...` 解析到本技能的模块。
"""

import sys
from pathlib import Path

SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / ".agents" / "skills" / "video-summary" / "scripts"
)
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
