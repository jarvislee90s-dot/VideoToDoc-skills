"""验证 video-summary/SKILL.md 步骤 6（合并）已迁出。

回归守卫：确保合并流程不会回到 video-summary，已归 video-to-slides 阶段 0。
"""
import re
from pathlib import Path

# 相对路径，适配 worktree 与原 repo
SKILL = Path(__file__).resolve().parents[2] / "SKILL.md"
text = SKILL.read_text(encoding="utf-8")


def assert_not_contains(pattern: str, label: str) -> None:
    assert not re.search(pattern, text), f"✗ {label} 不应存在（已迁到 video-to-slides）：{pattern}"


def assert_contains(pattern: str, label: str) -> None:
    assert re.search(pattern, text), f"✗ {label} 不存在：{pattern}"


# 步骤 6 不应是合并碎段（已迁到 video-to-slides/reference/merge_procedure.md）
assert_not_contains(r"6\.\s*\*\*合并转录碎段", "步骤 6 合并碎段")
assert_not_contains(r"prepare_merge", "prepare_merge 引用")
assert_not_contains(r"apply_merge", "apply_merge 引用")
assert_not_contains(r"review_merge", "review_merge 引用")
assert_not_contains(r"merge_review_report", "merge_review_report 引用")
assert_not_contains(r"reference/review_agent_prompt", "review_agent_prompt 引用")

# 步骤 6 现在是 Agent 摘要
assert_contains(r"6\.\s*\*\*Agent 摘要\*\*", "步骤 6 Agent 摘要")

# 步骤 6（Agent 摘要）应读 transcript.txt，不读 transcript_merged.json
assert_contains(r"Agent 读取 `transcript\.txt`", "摘要读 transcript.txt")
assert_not_contains(r"transcript_merged\.json", "transcript_merged.json 引用")

print("✓ video-summary SKILL.md 步骤 6 已正确迁出，步骤 6 现为 Agent 摘要")
