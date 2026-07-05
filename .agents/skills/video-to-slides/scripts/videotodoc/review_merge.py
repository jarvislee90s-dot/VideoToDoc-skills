#!/usr/bin/env python3
"""客观检查 merged_groups.json，输出 merge_review_report.json 供 review agent 参考。

检查项（均为客观指标，不做语义判断）：
1. 每段短句数是否超出 per_group_range；
2. 每段中文字符数是否落在 chars_per_group_range 区间内；
3. 相邻段边界是否存在明显的数字/程度补语断裂。

本脚本不调用大模型，也不决定如何分段；review agent 在此基础上做语义复核和综合判断。
"""
from __future__ import annotations
import json
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "_shared"))
from transcript_merge import normalize_raw  # noqa: E402

logger = logging.getLogger(__name__)


# 前段结尾出现这些强依存动词，且下一段开头是数字/百分比/倍数时，疑似补语被拆断
# 注意：不包含"是/了/到/为"等高频虚词，避免口语转录中大量误报
_SYNTAX_HINT_ENDINGS = (
    "上涨", "下降", "增长", "减少", "暴涨", "暴跌", "增加", "降低", "达到"
)

# 允许开头有“约、大概、大约、近、超过、不足”等限定词
_NUMBER_LIKE_RE = re.compile(
    r"^(约|大概|大约|近|超过|不足|至少|最多|最少|只有|仅)?\s*"
    r"[\d%.．一二三四五六七八九十百千万亿]+"
    r"(\s*(倍|个百分点|个点))?"
    r"|^翻了"
)


def _looks_like_complement(text: str) -> bool:
    """判断短句是否像是对前句的数量/程度补语。"""
    t = text.strip()
    if not t:
        return False
    if t.endswith(("%", "倍", "个百分点", "个点")):
        return True
    return bool(_NUMBER_LIKE_RE.match(t))


def _has_syntax_break(prev_group_text: str, next_group_first_text: str) -> bool:
    """简单启发式：前段以依存词结尾，下段开头是数量/程度补语。

    依存词后允许带口语中常见的"了"，如"暴涨了"后接"300%"仍视为断裂。
    """
    if not prev_group_text or not next_group_first_text:
        return False
    end = prev_group_text.rstrip("，。；：！？")
    if not any(end.endswith(h) or end.endswith(h + "了") for h in _SYNTAX_HINT_ENDINGS):
        return False
    return _looks_like_complement(next_group_first_text)


def _parse_range(value: str | dict, default_min: int, default_max: int) -> dict:
    """兼容字符串 '30-120' 和 dict {'min':30,'max':120}。"""
    if isinstance(value, dict):
        return {
            "min": int(value.get("min", default_min)),
            "max": int(value.get("max", default_max)),
        }
    if isinstance(value, str):
        parts = value.split("-")
        if len(parts) != 2:
            raise ValueError(f"range 字符串格式非法，应为 'min-max'：{value!r}")
        try:
            return {"min": int(parts[0]), "max": int(parts[1])}
        except ValueError as exc:
            raise ValueError(f"range 数值解析失败：{value!r}") from exc
    logger.warning(
        "无法识别的 range 类型 %r，回退到默认值 %d-%d",
        value,
        default_min,
        default_max,
    )
    return {"min": default_min, "max": default_max}


def review_groups(
    raw_segments: list[dict],
    groups: list[dict],
    constraints: dict,
) -> dict:
    """返回 review report，包含客观检查出的问题列表。"""
    per_range = _parse_range(constraints.get("per_group_range", "1-999"), 1, 999)
    chars_range = _parse_range(constraints.get("chars_per_group_range", "0-9999"), 0, 9999)

    issues = []
    for gi, g in enumerate(groups):
        idx = g.get("indices", [])
        text = g.get("text", "")
        char_count = len(text)

        if len(idx) > per_range["max"]:
            issues.append({
                "group_index": gi,
                "type": "group_size_exceeded",
                "severity": "warning",
                "description": f"第{gi}段包含{len(idx)}个短句，超出建议范围{per_range['min']}-{per_range['max']}。",
                "suggested_fix": f"整理 agent 可尝试在段内话题转换处切分，使每段短句数尽量落在{per_range['min']}-{per_range['max']}之间；若同话题过长可保留。",
            })

        if char_count > chars_range["max"]:
            issues.append({
                "group_index": gi,
                "type": "chars_above_max",
                "severity": "warning",
                "description": f"第{gi}段共{char_count}字，超出建议上限{chars_range['max']}字。",
                "suggested_fix": f"整理 agent 可按话题切分该段，使每段尽量落在{chars_range['min']}-{chars_range['max']}字之间。",
            })
        elif char_count < chars_range["min"] and len(idx) > 1:
            # 多短句合并后仍低于字数下限才提示；单短句本身可能就很短，属于正常
            issues.append({
                "group_index": gi,
                "type": "chars_below_min",
                "severity": "warning",
                "description": f"第{gi}段仅{char_count}字，低于建议下限{chars_range['min']}字。",
                "suggested_fix": "整理 agent 可考虑与相邻段合并，前提是不破坏话题完整。",
            })

    for gi in range(len(groups) - 1):
        prev_text = groups[gi].get("text", "")
        next_idx = groups[gi + 1].get("indices", [])
        if not next_idx:
            continue
        next_first_text = raw_segments[next_idx[0]].get("text", "")
        if _has_syntax_break(prev_text, next_first_text):
            issues.append({
                "group_index": gi,
                "type": "syntax_break",
                "severity": "critical",
                "description": (
                    f"第{gi}段结尾与第{gi+1}段开头存在句法断裂："
                    f"'{prev_text[-20:]}' 后接 '{next_first_text[:20]}'，"
                    "后者疑似前者的数量/程度补语，应并入同一段。"
                ),
                "suggested_fix": f"整理 agent 将 index {next_idx[0]} 的短句并入第{gi}段，或把相关补语整体移入同一段。",
            })

    critical_count = sum(1 for i in issues if i["severity"] == "critical")
    return {
        "total_groups": len(groups),
        "issues": issues,
        "pass": critical_count == 0,
    }


def main(
    transcript_path: str,
    groups_path: str,
    out_path: str | None = None,
) -> int:
    data = json.loads(Path(transcript_path).read_text(encoding="utf-8"))
    raw = data if isinstance(data, list) else data.get("segments", [])
    segs = normalize_raw(raw)

    groups = json.loads(Path(groups_path).read_text(encoding="utf-8"))

    merge_input_path = Path(groups_path).parent / "merge_input.json"
    if merge_input_path.exists():
        suggestion = json.loads(merge_input_path.read_text(encoding="utf-8")).get("suggestion", {})
    else:
        suggestion = {"per_group_range": "1-999", "chars_per_group_range": "0-9999"}

    constraints = {
        "per_group_range": suggestion.get("per_group_range", "1-999"),
        "chars_per_group_range": suggestion.get("chars_per_group_range", "0-9999"),
    }

    report = review_groups(segs, groups, constraints)
    out_path = out_path or str(Path(groups_path).parent / "merge_review_report.json")
    Path(out_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    critical_count = sum(1 for i in report["issues"] if i["severity"] == "critical")
    warning_count = len(report["issues"]) - critical_count
    print(f"  [review] 合并质量客观检查：{len(groups)} 段，critical {critical_count} 个，warning {warning_count} 个 -> {out_path}")
    for issue in report["issues"]:
        print(f"    [{issue['severity']}] [{issue['type']}] 第{issue['group_index']}段：{issue['description']}")

    # 只有 critical 问题才返回非 0；warning 允许整理 agent 酌情处理，不阻断流程
    return 0 if critical_count == 0 else 1


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript")
    ap.add_argument("groups")
    ap.add_argument("-o", "--output", default=None)
    a = ap.parse_args()
    sys.exit(main(a.transcript, a.groups, a.output))
