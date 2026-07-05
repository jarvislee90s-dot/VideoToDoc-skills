"""校验 merge_review_report.json 必须含 self_review 键。"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_review_report import check  # noqa: E402


def _write(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "merge_review_report.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def test_missing_self_review_key_returns_nonzero(tmp_path):
    """无 self_review 键 → 视为 review 未完成，非零退出。"""
    p = _write(tmp_path, {"pass": True, "total_groups": 10})  # 故意缺 self_review
    assert check(p) != 0


def test_self_review_false_path_a_passes(tmp_path):
    """路径 A（子代理）self_review=False → 通过。"""
    p = _write(tmp_path, {"pass": True, "self_review": False, "total_groups": 10})
    assert check(p) == 0


def test_self_review_true_path_b_passes(tmp_path):
    """路径 B（自审）self_review=True → 通过。"""
    p = _write(tmp_path, {"pass": True, "self_review": True, "total_groups": 10})
    assert check(p) == 0


def test_non_bool_self_review_returns_nonzero(tmp_path):
    """self_review 不是 bool → 非零。"""
    p = _write(tmp_path, {"pass": True, "self_review": "false"})  # 字符串，非法
    assert check(p) != 0


def test_missing_report_returns_nonzero(tmp_path):
    """报告文件不存在 → 非零。"""
    assert check(tmp_path / "merge_review_report.json") != 0
