"""测试公共配置：将 video-summary 的 scripts 目录注入 sys.path。

pytest.ini 的 pythonpath 只包含 video-to-slides/scripts 与 _shared，
不含 video-summary/scripts，因此这里手动前置插入，
保证 `from sources import ...` 解析到本技能的模块。

注意：video-to-slides/scripts 下存在同名 process.py，且其测试
（test_pipeline_parallel 等）在全量回归中先执行 `import process`，
会把 sys.modules['process'] 绑定到对方模块。因此测试 video-summary 的
process 时不要直接 `import process`，改用下方 vs_process 夹具
（importlib 以独立模块名从绝对路径加载，参照 test_process_run_naming.py 模式）。
"""

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / ".agents" / "skills" / "video-summary" / "scripts"
)
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

_VS_PROCESS_MODULE_NAME = "video_summary_process_tests"


def _load_vs_process():
    """以独立模块名加载 video-summary 的 process.py，规避 sys.modules 命名冲突。"""
    if _VS_PROCESS_MODULE_NAME in sys.modules:
        return sys.modules[_VS_PROCESS_MODULE_NAME]
    spec = importlib.util.spec_from_file_location(
        _VS_PROCESS_MODULE_NAME, SCRIPTS_DIR / "process.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[_VS_PROCESS_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def vs_process():
    """video-summary 的 process 模块（勿用 `import process`：会被 video-to-slides 同名模块污染）。"""
    return _load_vs_process()
