"""验证 video-to-slides/SKILL.md 阶段 3 收尾用 finalize.py wrapper。"""
import re
from pathlib import Path

SKILL = Path("/Users/jarvis/Documents/VideoToDoc-skills/.agents/skills/video-to-slides/SKILL.md")
text = SKILL.read_text(encoding="utf-8")


def assert_contains(pattern: str, label: str) -> None:
    assert re.search(pattern, text), f"✗ {label} 不存在：{pattern}"


def assert_not_contains(pattern: str, label: str) -> None:
    assert not re.search(pattern, text), f"✗ {label} 不应存在：{pattern}"


# 必须有阶段 3 描述提到 finalize.py
assert_contains(r"finalize\.py", "阶段 3 收尾提到 finalize.py")

# 必须有"统一入口/统一脚本/wrapper/不需要分别跑"等描述
assert_contains(r"(统一入口|统一脚本|wrapper|不需要分别跑|不需要单独跑)", "阶段 3 wrapper 描述")

# 不应再有单独的 ⑧ 恢复图片并同步目录 / ⑨ 渲染导图 作为独立步
assert_not_contains(r"### ⑧ 恢复图片并同步目录", "独立 ⑧ 步")
assert_not_contains(r"### ⑨ 渲染导图", "独立 ⑨ 步")

print("✓ SKILL.md 阶段 3 收尾验证通过")
