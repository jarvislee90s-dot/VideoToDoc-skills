"""验证 video-summary/SKILL.md 6.6 节精简 + 引用 reference。"""
import re
from pathlib import Path

SKILL = Path("/Users/jarvis/Documents/VideoToDoc-skills/.agents/skills/video-summary/SKILL.md")
text = SKILL.read_text(encoding="utf-8")


def assert_contains(pattern: str, label: str) -> None:
    assert re.search(pattern, text), f"✗ {label} 不存在：{pattern}"


def assert_not_contains(pattern: str, label: str) -> None:
    assert not re.search(pattern, text), f"✗ {label} 不应存在：{pattern}"


# 6.6 节标题必须有"必做，不可跳过"（加粗）
assert_contains(r"### 6\.6 Review Agent.*\*\*必做，不可跳过\*\*", "6.6 节必做标识")

# 6.6 节不应有"为什么强制"段
assert_not_contains(r"## 为什么强制", "6.6 节'为什么强制'段")

# 6.6 节应引用 reference/review_agent_prompt.md
assert_contains(r"reference/review_agent_prompt\.md", "6.6 节引用 reference")

# 6.6 节应有"review agent 规则"小节（文档用加粗样式）
assert_contains(r"review agent 规则", "6.6 节规则小节")

# 6.6 节不应内联完整 prompt 模板（清单 5 项不应出现在 SKILL.md）
inline_template_count = text.count("### 1. 句法完整性")
assert inline_template_count == 0, \
    f"✗ 6.6 节不应内联 prompt 模板（发现 {inline_template_count} 处），应指向 reference/"

print("✓ SKILL.md 6.6 节验证通过")
