"""测试 finalize.py wrapper 脚本。"""
import sys
from pathlib import Path

# 把 scripts/ 加到 sys.path 以便导入 finalize
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import finalize  # noqa: E402


def test_find_compact_and_semantic(tmp_path):
    """glob 找紧凑版和整理版。"""
    (tmp_path / "video_讲义_紧凑版_20260705.md").write_text("compact")
    (tmp_path / "video_讲义_整理版_20260705.md").write_text("semantic")
    compact, semantic = finalize.find_compact_and_semantic(tmp_path)
    assert compact.name == "video_讲义_紧凑版_20260705.md"
    assert semantic.name == "video_讲义_整理版_20260705.md"


def test_find_compact_and_semantic_missing(tmp_path):
    """缺文件时抛 FileNotFoundError。"""
    import pytest
    with pytest.raises(FileNotFoundError, match="找不到紧凑版"):
        finalize.find_compact_and_semantic(tmp_path)


def test_main_no_args(capsys):
    """main() 无参数时打印 usage 并返回 1。"""
    rc = finalize.main([])
    assert rc == 1
    captured = capsys.readouterr()
    assert "用法：python3 finalize.py" in captured.err


def test_main_nonexistent_run_dir(capsys):
    """run_dir 不存在时返回 2。"""
    rc = finalize.main(["/tmp/nonexistent_run_dir_xyz_finalize_test"])
    assert rc == 2
    captured = capsys.readouterr()
    assert "run_dir 不存在" in captured.err
