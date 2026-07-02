# 转录合并 Review Agent 实现计划

> **面向 Agent 工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 按任务逐项实现。步骤使用复选框（`- [ ]`）语法以便跟踪。

**目标：** 在 video-summary 的 transcript 语义合并步骤中增加独立 review agent，检查句法完整性、段内短句数、字数区间，输出 review report 供整理 agent 修正，解决“一句话被拆两段”等质量问题。

**架构：** prepare_merge.py 在生成 merge_input.json 时同步输出 `suggestion` 中的动态约束（目标段数、per_group_range、chars_per_group_range）。整理 agent 按增强后的 SKILL.md 规则生成 merged_groups.json；apply_merge.py 校验 index 后，review_merge.py 先做客观检查输出初步报告；review agent（独立上下文 LLM）读取 merge_input.json + merged_groups.json + 初步报告，输出 `merge_review_report.json`；整理 agent 根据 report 局部修正分组。所有分段决策权在 agent，脚本只提供约束参考与客观指标。

**技术栈：** Python 3.9+、pytest、json。

## 全局约束

- 保持现有 `transcript_merge` 共享模块接口向后兼容，新增字段不影响下游消费。
- review agent 只输出报告，不直接修改 `merged_groups.json`。
- 字数约束采用动态柔性区间（按视频时长），不使用固定的 `max_segment_chars=400 / min_segment_chars=30`。
- 脚本只计算约束和客观指标，不做分段决策；分段逻辑由整理 agent 和 review agent 综合语义判断。
- 所有新行为必须有测试覆盖。
- 代码注释使用中文；文档和计划使用中文。

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `.agents/skills/_shared/transcript_merge/__init__.py` | 在 `suggest_segments` 中增加 `chars_per_group_range` 字段。 |
| `.agents/skills/video-summary/scripts/prepare_merge.py` | 输出的 `merge_input.json` 中 `suggestion` 包含 `chars_per_group_range`。 |
| `.agents/skills/video-summary/scripts/review_merge.py` | 新增 CLI：读取 transcript + merged_groups，做客观检查（短句数、字数区间、边界数字依存），输出初步 `merge_review_report.json` 供 review agent 参考。 |
| `.agents/skills/video-summary/SKILL.md` | 增强 ⑤.5 合并规则；新增 ⑤.6 Review Agent 步骤；新增 ⑤.7 整理 agent 根据报告修正步骤。 |
| `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_transcript_merge.py` | 补充 `chars_per_group_range` 测试。 |
| `.agents/skills/video-summary/scripts/tests/test_review_merge.py` | 新增 `review_merge.py` 测试。 |

---

### Task 1：动态字数区间写入 merge_input.json

**文件：**
- 修改：`.agents/skills/_shared/transcript_merge/__init__.py`
- 修改：`.agents/skills/video-summary/scripts/prepare_merge.py`（无需改动，自动透传 suggestion）
- 测试：`.agents/skills/video-to-slides/scripts/videotodoc/tests/test_transcript_merge.py`

**接口：**
- 消费：`suggest_segments(duration_ms)` 内部新增字数区间计算逻辑。
- 产出：`suggest_segments` 返回字典新增 `chars_per_group_range: str`（如 `"50-180"`）；`prepare_merge.py` 输出的 `merge_input.json` 自动包含该字段。

- [ ] **步骤 1：编写失败测试**

追加到 `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_transcript_merge.py`：

```python
class TestSuggestSegments:
    def test_short_11min(self):
        s = suggest_segments(690_000)  # 11.5min
        assert s["target_segments"] == 34
        assert s["per_group_range"] == "3-8"
        assert s["max_segments"] == 120
        assert s["chars_per_group_range"] == "30-120"

    def test_1h(self):
        s = suggest_segments(3_600_000)
        assert s["target_segments"] == 90
        assert s["max_segments"] == 120
        assert s["chars_per_group_range"] == "80-270"

    def test_2h(self):
        s = suggest_segments(7_200_000)
        assert s["max_segments"] == 240
        assert s["target_segments"] == 144
        assert s["chars_per_group_range"] == "120-400"

    def test_tiny_video_floor(self):
        s = suggest_segments(60_000)  # 1min
        assert s["target_segments"] >= 8
        assert s["chars_per_group_range"] == "30-120"
```

- [ ] **步骤 2：运行测试确认失败**

运行：
```bash
cd /Users/jarvis/Documents/VideoToDoc-skills
PYTHONPATH=".agents/skills/video-to-slides/scripts:.agents/skills/_shared" \
  .venv/bin/python3 -m pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_transcript_merge.py::TestSuggestSegments -v
```

预期：`test_short_11min` 等 FAIL，提示 `KeyError: 'chars_per_group_range'`。

- [ ] **步骤 3：实现最小改动**

修改 `.agents/skills/_shared/transcript_merge/__init__.py` 中的 `suggest_segments`：

```python
def suggest_segments(duration_ms: int) -> dict:
    """按视频时长决定目标段数建议、每段短句数范围和字数区间。段数为软目标，同话题完整优先。"""
    duration_sec = duration_ms / 1000
    duration_min = duration_sec / 60
    if duration_min <= 15:
        target = max(8, int(duration_sec / 20))
        per_group = "3-8"
        chars_range = "30-120"
    elif duration_min <= 30:
        target = max(12, int(duration_sec / 30))
        per_group = "5-12"
        chars_range = "50-180"
    elif duration_min <= 60:
        target = max(20, int(duration_sec / 40))
        per_group = "8-18"
        chars_range = "80-270"
    else:
        target = max(30, int(duration_sec / 50))
        per_group = "12-25"
        chars_range = "120-400"
    max_seg = int(duration_min * 2) if duration_min > 60 else 120
    target = min(target, max_seg)
    return {
        "target_segments": target,
        "per_group_range": per_group,
        "max_segments": max_seg,
        "chars_per_group_range": chars_range,
    }
```

- [ ] **步骤 4：运行测试确认通过**

运行：
```bash
cd /Users/jarvis/Documents/VideoToDoc-skills
PYTHONPATH=".agents/skills/video-to-slides/scripts:.agents/skills/_shared" \
  .venv/bin/python3 -m pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_transcript_merge.py::TestSuggestSegments -v
```

预期：4 个测试全部 PASS。

- [ ] **步骤 5：验证 prepare_merge 输出包含新字段**

运行：
```bash
cd /Users/jarvis/Documents/VideoToDoc-skills
.venv/bin/python3 .agents/skills/video-summary/scripts/prepare_merge.py \
  runs/内存暴涨，谁在哭？谁在笑？_20260701_075505/transcript.json \
  -o /tmp/test_merge_input.json
.venv/bin/python3 -c "import json; d=json.load(open('/tmp/test_merge_input.json')); print(d['suggestion'])"
```

预期输出包含 `chars_per_group_range` 字段。

- [ ] **步骤 6：Commit**

```bash
cd /Users/jarvis/Documents/VideoToDoc-skills
git add .agents/skills/_shared/transcript_merge/__init__.py \
        .agents/skills/video-to-slides/scripts/videotodoc/tests/test_transcript_merge.py
git commit -m "feat(transcript_merge): 按视频时长增加每段字数区间建议"
```

---

### Task 2：新增 review_merge.py 客观检查脚本

**文件：**
- 创建：`.agents/skills/video-summary/scripts/review_merge.py`
- 创建：`.agents/skills/video-summary/scripts/tests/test_review_merge.py`
- 依赖 Task 1 的 `suggestion.chars_per_group_range`

**接口：**
- 消费：`transcript.json`（原始碎段）、`merged_groups.json`（整理 agent 分组）、`merge_input.json`（含 suggestion）。
- 产出：`merge_review_report.json`，字段包括 `total_groups`、`issues`（含 `group_index`、`type`、`severity`、`description`、`suggested_fix`）、`pass`。本脚本不调用大模型，只输出客观指标。

- [ ] **步骤 1：编写失败测试**

创建 `.agents/skills/video-summary/scripts/tests/test_review_merge.py`：

```python
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "_shared"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from review_merge import review_groups  # noqa: E402


class TestReviewGroups:
    def test_group_size_exceeded(self):
        segs = [{"text": "x"} for _ in range(20)]
        groups = [{"indices": list(range(20)), "text": "".join(s["text"] for s in segs)}]
        constraints = {"per_group_range": {"min": 3, "max": 8}, "chars_per_group_range": {"min": 30, "max": 120}}
        report = review_groups(segs, groups, constraints)
        assert report["pass"] is False
        assert any(i["type"] == "group_size_exceeded" for i in report["issues"])

    def test_chars_above_max(self):
        segs = [{"text": "这是一个很长的句子。" * 20}]
        groups = [{"indices": [0], "text": segs[0]["text"]}]
        constraints = {"per_group_range": {"min": 1, "max": 5}, "chars_per_group_range": {"min": 10, "max": 50}}
        report = review_groups(segs, groups, constraints)
        assert any(i["type"] == "chars_above_max" for i in report["issues"])

    def test_chars_below_min(self):
        segs = [{"text": "短"}]
        groups = [{"indices": [0], "text": "短"}]
        constraints = {"per_group_range": {"min": 1, "max": 5}, "chars_per_group_range": {"min": 30, "max": 120}}
        report = review_groups(segs, groups, constraints)
        assert any(i["type"] == "chars_below_min" for i in report["issues"])

    def test_syntax_break_number(self):
        segs = [
            {"text": "价格基本都暴涨了"},
            {"text": "300%到500%"},
            {"text": "最夸张的"},
        ]
        groups = [
            {"indices": [0], "text": "价格基本都暴涨了"},
            {"indices": [1, 2], "text": "300%到500%，最夸张的"},
        ]
        constraints = {"per_group_range": {"min": 1, "max": 8}, "chars_per_group_range": {"min": 30, "max": 120}}
        report = review_groups(segs, groups, constraints)
        assert any(i["type"] == "syntax_break" for i in report["issues"])

    def test_pass_clean(self):
        segs = [{"text": "短句一"}, {"text": "短句二"}]
        groups = [{"indices": [0, 1], "text": "短句一，短句二"}]
        constraints = {"per_group_range": {"min": 1, "max": 8}, "chars_per_group_range": {"min": 10, "max": 120}}
        report = review_groups(segs, groups, constraints)
        assert report["pass"] is True
        assert report["issues"] == []
```

- [ ] **步骤 2：运行测试确认失败**

运行：
```bash
cd /Users/jarvis/Documents/VideoToDoc-skills
PYTHONPATH=".agents/skills/video-to-slides/scripts:.agents/skills/_shared:.agents/skills/video-summary/scripts" \
  .venv/bin/python3 -m pytest .agents/skills/video-summary/scripts/tests/test_review_merge.py -v
```

预期：`ModuleNotFoundError: No module named 'review_merge'`。

- [ ] **步骤 3：实现 review_merge.py**

创建 `.agents/skills/video-summary/scripts/review_merge.py`：

```python
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
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_shared"))
from transcript_merge import normalize_raw  # noqa: E402


# 前段结尾出现这些词，且下一段开头是数字/百分比/倍数时，疑似补语被拆断
_SYNTAX_HINT_ENDINGS = (
    "上涨", "下降", "增长", "减少", "暴涨", "暴跌", "增加", "降低", "达到", "为", "是", "了", "到"
)

_NUMBER_LIKE_RE = re.compile(r"^[\d%.．．一二三四五六七八九十百千万亿]+|^\d+倍|^翻了")


def _looks_like_complement(text: str) -> bool:
    """判断短句是否像是对前句的数量/程度补语。"""
    t = text.strip()
    return bool(_NUMBER_LIKE_RE.match(t)) or t.endswith(("%", "倍"))


def _has_syntax_break(prev_group_text: str, next_group_first_text: str) -> bool:
    """简单启发式：前段以依存词结尾，下段开头是数量/程度补语。"""
    if not prev_group_text or not next_group_first_text:
        return False
    end = prev_group_text.rstrip("，。；：！？")
    if not any(end.endswith(h) for h in _SYNTAX_HINT_ENDINGS):
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
        return {"min": int(parts[0]), "max": int(parts[1])}
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
            # 单短句且字数少属于正常，不提示
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

    return {
        "total_groups": len(groups),
        "issues": issues,
        "pass": len(issues) == 0,
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

    severity_emoji = {"critical": "🔴", "warning": "🟡"}
    print(f"  🔍 合并质量客观检查：{len(groups)} 段，发现 {len(report['issues'])} 个问题 → {out_path}")
    for issue in report["issues"]:
        print(f"    {severity_emoji.get(issue['severity'], '⚪')} [{issue['type']}] 第{issue['group_index']}段：{issue['description']}")

    return 0 if report["pass"] else 1


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript")
    ap.add_argument("groups")
    ap.add_argument("-o", "--output", default=None)
    a = ap.parse_args()
    sys.exit(main(a.transcript, a.groups, a.output))
```

- [ ] **步骤 4：运行测试确认通过**

运行：
```bash
cd /Users/jarvis/Documents/VideoToDoc-skills
PYTHONPATH=".agents/skills/video-to-slides/scripts:.agents/skills/_shared:.agents/skills/video-summary/scripts" \
  .venv/bin/python3 -m pytest .agents/skills/video-summary/scripts/tests/test_review_merge.py -v
```

预期：5 个测试全部 PASS。

- [ ] **步骤 5：在真实 run 目录上验证**

运行：
```bash
cd /Users/jarvis/Documents/VideoToDoc-skills
.venv/bin/python3 .agents/skills/video-summary/scripts/review_merge.py \
  runs/内存暴涨，谁在哭？谁在笑？_20260701_075505/transcript.json \
  runs/内存暴涨，谁在哭？谁在笑？_20260701_075505/merged_groups.json \
  -o /tmp/test_review_report.json
```

预期：输出中包含针对“价格基本都暴涨了”+“300%到500%”的 `syntax_break` critical 问题，以及若干 `group_size_exceeded` / `chars_above_max` warning。

- [ ] **步骤 6：Commit**

```bash
cd /Users/jarvis/Documents/VideoToDoc-skills
git add .agents/skills/video-summary/scripts/review_merge.py \
        .agents/skills/video-summary/scripts/tests/test_review_merge.py
git commit -m "feat(video-summary): 增加 review_merge.py 客观检查脚本"
```

---

### Task 3：增强 SKILL.md 合并规则并增加 Review Agent 步骤

**文件：**
- 修改：`.agents/skills/video-summary/SKILL.md`

**接口：**
- 消费：Task 1 的 `merge_input.json`（含 `chars_per_group_range`）；Task 2 的 `review_merge.py` 输出。
- 产出：整理 agent 和 review agent 都能看到的统一约束文档；review agent 输出 `merge_review_report.json`。

- [ ] **步骤 1：备份并读取当前 SKILL.md 合并相关段落**

确认当前 `.agents/skills/video-summary/SKILL.md` 第 55-94 行为 ⑥ 合并转录碎段步骤。

- [ ] **步骤 2：扩展合并规则**

将第 72-81 行的合并规则替换为以下内容：

```markdown
**合并规则**（严格遵守）：
1. **原文保留**：完整保留每个短句的原文字，不删字、不改字、不加字、不调换顺序。
   你只在短句连接处插入标点。
2. **标点连接**：短句间加合适标点——逗号（停顿/并列/分句）、句号（句末）、
   分号（并列长句）、问号/感叹号（原句语气）、冒号（引出）。保留原问号感叹号。
3. **同话题聚合（最高优先级）**：描述同一件事/同一话题的相邻短句必须整到一段。
   话题转换处断段。宁可段数偏离目标，也要保证同话题完整。
4. **句法完整性（最高优先级）**：禁止把一个完整句子的依存成分拆到两段。
   以下情况必须并入同一段：
   - 程度/数量补语：如“价格暴涨了”与“300%到500%”；
   - 数量宾语：如“达到了”与“50亿美元”；
   - 时间/地点状语紧接说明：如“发生在”与“2024年”；
   - 列举项：同一组并列数据或例子不要拆散。
5. **段数软目标**：参考 `suggestion.target_segments` 和 `suggestion.per_group_range`。
   段数是软目标——同话题完整优先于凑段数。硬上限 `max_segments` 不可超。
6. **每段短句数约束**：尽量使每段包含的短句数落在 `suggestion.per_group_range` 范围内。
   若同话题较长，允许超出，但需在输出前自检并说明理由。
7. **每段字数区间**：每段合并后的中文字符数（含标点）建议落在 `suggestion.chars_per_group_range` 区间内。
   该区间是柔性参考，同话题完整优先；若必须超出，优先在同话题内部切分，而非强行压缩或跨话题拆断。
8. **索引完整**：indices 从 0 连续到末尾，覆盖全部短句，不重不漏；每段内连续递增。
```

- [ ] **步骤 3：在合并步骤后插入 Review Agent 步骤**

在第 94 行“注意”段落之后、第 96 行“7. Agent 摘要”之前，插入：

```markdown
### ⑤.6 Review Agent 复核合并质量

**背景**：整理 agent 第一次合并可能忽略句法依存或字数约束。由另一个独立上下文的 review agent 检查 `merged_groups.json`，输出 `merge_review_report.json`，整理 agent 根据报告局部修正。review agent 不直接修改 `merged_groups.json`，只输出意见；分段决策权始终在 agent。

**步骤**：
1. 整理 agent 完成首次合并后，运行客观检查脚本生成初步报告：
   python3 .agents/skills/video-summary/scripts/review_merge.py \
     runs/<run_dir>/transcript.json runs/<run_dir>/merged_groups.json
2. review agent 读取：
   - `runs/<run_dir>/merge_input.json`（原始短句 + suggestion 约束）
   - `runs/<run_dir>/merged_groups.json`（整理 agent 输出）
   - `runs/<run_dir>/merge_review_report.json`（客观检查初步结果）
3. review agent 按以下清单复核，输出增强版 `merge_review_report.json`：
   - **句法完整性**：相邻段边界是否把补语/数据/宾语拆散；
   - **同话题聚合**：同一话题是否被不必要地切到两段；
   - **短句数**：每段是否尽量落在 `per_group_range` 内；
   - **字数**：每段是否尽量落在 `chars_per_group_range` 内；
   - **原始短句索引**：是否连续覆盖、无跳号。
4. review report 格式示例：
   {
     "total_groups": 69,
     "issues": [
       {
         "group_index": 6,
         "type": "syntax_break",
         "severity": "critical",
         "description": "第6段结尾'价格基本都暴涨了'与第7段开头'300%到500%'是依存关系，应并入同一段",
         "suggested_fix": "整理 agent 将 index 83 并入第7段，或将 index 84-86 并入第6段"
       }
     ],
     "pass": false
   }

**review agent 规则**：
- 只输出报告，不直接修改 `merged_groups.json`。
- critical 问题必须标记；warning 问题允许整理 agent 酌情处理。
- 所有判断必须基于 `merge_input.json` 中的约束数据，不能自行放宽。
- 遇到超出 `chars_per_group_range` 或 `per_group_range` 的段，先判断是否为“同话题完整”导致；若是，可接受为 warning；若不是，应建议切分。

### ⑤.7 整理 agent 根据 Review Report 修正

**步骤**：
1. 读取 `merge_review_report.json`；
2. 只修改 report 中标记的问题分组，其余分组保持不变；
3. 修正后重跑 `apply_merge.py` 校验 index；
4. 再次运行 `review_merge.py` 与 review agent，直到 `pass` 为 true 或只剩可接受的 warning；
5. 最终产物为 `transcript_merged.json`。

**修正原则**：
- critical 的 `syntax_break` 必须修复；
- `group_size_exceeded` / `chars_above_max` / `chars_below_min` 优先通过“在同话题内部切分/合并”解决，不要跨话题拆断；
- 若某段因同话题完整而必须超出区间，保留并说明理由。
```

- [ ] **步骤 4：更新默认命令/流程中的步骤编号**

将原“7. Agent 摘要”改为“8. Agent 摘要”，并确保后续步骤编号顺延。

- [ ] **步骤 5：验证 SKILL.md 渲染正常**

运行：
```bash
cd /Users/jarvis/Documents/VideoToDoc-skills
.venv/bin/python3 -c "import markdown; markdown.markdown(open('.agents/skills/video-summary/SKILL.md').read())" && echo "SKILL.md OK"
```

预期：无异常，输出 `SKILL.md OK`。

- [ ] **步骤 6：Commit**

```bash
cd /Users/jarvis/Documents/VideoToDoc-skills
git add .agents/skills/video-summary/SKILL.md
git commit -m "docs(video-summary): 增加合并约束与 review agent 步骤"
```

---

### Task 4：端到端回归验证

**文件：**
- 复用已有 run 目录：`runs/内存暴涨，谁在哭？谁在笑？_20260701_075505`

**接口：**
- 消费：Task 1-3 的全部改动。
- 产出：确认 review 流程能捕获已知问题，且整理 agent 可按 report 修正。

- [ ] **步骤 1：运行 prepare_merge 确认新字段**

```bash
cd /Users/jarvis/Documents/VideoToDoc-skills
.venv/bin/python3 .agents/skills/video-summary/scripts/prepare_merge.py \
  runs/内存暴涨，谁在哭？谁在笑？_20260701_075505/transcript.json \
  -o /tmp/e2e_merge_input.json
.venv/bin/python3 -c "
import json
d = json.load(open('/tmp/e2e_merge_input.json'))
assert 'chars_per_group_range' in d['suggestion']
print('chars_per_group_range =', d['suggestion']['chars_per_group_range'])
"
```

预期：输出 `chars_per_group_range = 50-180`（22 分钟落在 ≤30min 区间）。

- [ ] **步骤 2：运行 review_merge 确认捕获 syntax_break**

```bash
cd /Users/jarvis/Documents/VideoToDoc-skills
.venv/bin/python3 .agents/skills/video-summary/scripts/review_merge.py \
  runs/内存暴涨，谁在哭？谁在笑？_20260701_075505/transcript.json \
  runs/内存暴涨，谁在哭？谁在笑？_20260701_075505/merged_groups.json \
  -o /tmp/e2e_review_report.json
.venv/bin/python3 -c "
import json
r = json.load(open('/tmp/e2e_review_report.json'))
assert any(i['type'] == 'syntax_break' for i in r['issues']), '未捕获 syntax_break'
print('捕获 syntax_break，总问题数：', len(r['issues']))
"
```

预期：输出显示存在 syntax_break，总问题数 ≥1。

- [ ] **步骤 3：跑全量相关测试**

```bash
cd /Users/jarvis/Documents/VideoToDoc-skills
PYTHONPATH=".agents/skills/video-to-slides/scripts:.agents/skills/_shared:.agents/skills/video-summary/scripts" \
  .venv/bin/python3 -m pytest \
  .agents/skills/video-to-slides/scripts/videotodoc/tests/test_transcript_merge.py \
  .agents/skills/video-summary/scripts/tests/test_review_merge.py -v
```

预期：全部 PASS。

- [ ] **步骤 4：Commit（如测试通过）**

```bash
cd /Users/jarvis/Documents/VideoToDoc-skills
git commit -m "test: transcript merge review 端到端回归验证" --allow-empty
```

---

## 自检

**1. 规格覆盖度：**
- 动态柔性字数区间 → Task 1
- review agent 独立上下文 → Task 3 的 ⑤.6
- review agent 只出报告 → Task 3 的 review agent 规则
- 整理 agent 做修正 → Task 3 的 ⑤.7
- 整理 agent 和 review agent 都能看到约束 → Task 3 在 SKILL.md 中统一写明
- 不使用固定 400/30 → Task 1 使用动态 chars_per_group_range
- 脚本只提供约束/客观指标，不做分段决策 → Task 1-2 描述与实现

**2. Placeholder 扫描：** 无 TBD/TODO/“实现 later”/“类似 Task N”。

**3. 类型一致性：** `suggest_segments` 返回字段、`review_groups` 参数、`merge_review_report.json` 字段在 Task 1-3 中保持一致。
