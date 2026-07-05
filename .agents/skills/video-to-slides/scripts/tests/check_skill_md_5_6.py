"""验证 video-to-slides/SKILL.md ⑤⑥ 步内容更新。"""
import re
from pathlib import Path

SKILL = Path("/Users/jarvis/Documents/VideoToDoc-skills/.agents/skills/video-to-slides/SKILL.md")
text = SKILL.read_text(encoding="utf-8")


def assert_contains(pattern: str, label: str) -> None:
    assert re.search(pattern, text), f"✗ {label} 不存在：{pattern}"


def assert_not_contains(pattern: str, label: str) -> None:
    assert not re.search(pattern, text), f"✗ {label} 不应存在：{pattern}"


# ⑤ 步必须有"必做，不可跳过"（加粗 **）
assert_contains(r"### ⑤ 生成全文目录.*\*\*必做，不可跳过\*\*", "⑤ 步必做标识")

# ⑤ 步必须明确"目录只写一次到紧凑版"（加粗样式，与文档一致）
assert_contains(r"目录\*\*只写一次\*\*到\*\*紧凑版\*\*", "⑤ 步只写一次约束")

# ⑤ 步必须提到"⑥ 步会复制到整理版"
assert_contains(r"⑥ 步会.*复制到整理版", "⑤ 步提示 ⑥ 步复制")

# ⑥ 步必须有"必做，不可跳过"
assert_contains(r"### ⑥ 语义整理.*\*\*必做，不可跳过\*\*", "⑥ 步必做标识")

# ⑥ 步必须包含"从紧凑版复制目录到整理版"任务
assert_contains(r"任务 1：从紧凑版复制目录到整理版", "⑥ 步任务 1")

# ⑥ 步不能再说"改写完成后运行脚本恢复图片并同步目录"
assert_not_contains(r"改写完成后，运行脚本恢复图片并同步目录", "⑥ 步旧描述")

# ⑥ 步不能提到 --no-sync-toc 标志
assert_not_contains(r"--no-sync-toc", "⑥ 步 --no-sync-toc")

print("✓ SKILL.md ⑤⑥ 步内容验证通过")
