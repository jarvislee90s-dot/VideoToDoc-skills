"""校验 merge_review_report.json 必须含 self_review 键。

review_agent_prompt.md 要求路径 A 写 self_review=false、路径 B 写 true。
缺失该键即视为 review 未标注执行路径，等同未完成，不得进入下一步。

用法：python3 check_review_report.py <run_dir>
退出码：0 通过；1 self_review 缺失/类型错；2 报告不存在。
"""
import json
import sys
from pathlib import Path


def check(report_path: Path) -> int:
    """校验单份 review 报告，返回退出码。"""
    if not report_path.exists():
        print(f"❌ 找不到 review 报告：{report_path}", file=sys.stderr)
        return 2
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"❌ {report_path.name} 不是合法 JSON：{e}", file=sys.stderr)
        return 1
    if "self_review" not in report:
        print(
            f"❌ {report_path.name} 缺少 self_review 键：review 未标注执行路径，视为未完成。",
            file=sys.stderr,
        )
        return 1
    if not isinstance(report["self_review"], bool):
        print(
            f"❌ {report_path.name} 的 self_review 必须是 bool，"
            f"当前：{type(report['self_review']).__name__}",
            file=sys.stderr,
        )
        return 1
    label = "A（独立子代理）" if report["self_review"] is False else "B（自审 fallback）"
    print(f"✓ self_review={report['self_review']}（路径 {label}）")
    return 0


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print("用法：python3 check_review_report.py <run_dir>", file=sys.stderr)
        return 2
    run_dir = Path(args[0]).expanduser().resolve()
    if not run_dir.is_dir():
        print(f"❌ run_dir 不存在：{run_dir}", file=sys.stderr)
        return 2
    return check(run_dir / "merge_review_report.json")


if __name__ == "__main__":
    raise SystemExit(main())
