"""验证 restore_images.py 删除了 sync_toc 功能（目录由 Agent 自己写/复制）。"""
import importlib.util
import inspect
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "restore_images.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("restore_images", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_sync_toc_function_removed():
    mod = _load_module()
    assert not hasattr(mod, "sync_toc"), "sync_toc 函数应该被删除（目录由 agent 写）"


def test_extract_toc_from_compact_removed():
    mod = _load_module()
    assert not hasattr(mod, "extract_toc_from_compact"), \
        "extract_toc_from_compact 函数应该被删除"


def test_no_sync_toc_argument():
    mod = _load_module()
    sig = inspect.signature(mod.restore_images)
    assert "sync_toc_enabled" not in sig.parameters, \
        "restore_images 不应有 sync_toc_enabled 参数"


def test_main_no_no_sync_toc_help():
    """main() 的 usage/help 字符串不应包含 --no-sync-toc。"""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "--no-sync-toc" not in text, \
        "main() usage/help 不应再提到 --no-sync-toc 标志"
