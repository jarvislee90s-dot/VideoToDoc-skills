# 合并质量修复实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 修复 video-summary + video-to-slides 流程中的两个 bug（restore_images.py 误覆盖目录、合并违反句法完整性）和两个流程问题（阶段 3 收尾重复命令、review agent prompt 与流程混在一起）。

**架构：** 删 `restore_images.py` 的 sync_toc 同步目录功能（Agent 自己写/复制目录）；新增 `finalize.py` wrapper 包装阶段 3 收尾；新增 `reference/review_agent_prompt.md` 独立 review agent prompt；重写两份 SKILL.md 把流程强化为"必做，不可跳过"。

**Tech Stack:** Python 3.14, pytest, Bash

## Global Constraints

- 严格 TDD：每任务先写测试，再写实现，再验证，再 commit
- 测试验收总表见文末（明确每个测试用例的输入、命令、预期结果）
- 文档类任务用 `grep`/`python -c` 验证关键字存在，无独立测试框架
- 保持现有目录结构（不改 `process.py` / `cli.py` / `document.py` / `review_merge.py`）
- 每次 commit 信息用中文，格式 `type(scope): 描述`
- 全程在 worktree 内工作

## 文件结构

| 文件 | 类型 | 职责 |
|---|---|---|
| `agents/skills/video-to-slides/scripts/restore_images.py` | 修改 | 删 sync_toc + extract_toc_from_compact；只保留图片恢复 |
| `agents/skills/video-to-slides/scripts/finalize.py` | 新增 | 阶段 3 收尾 wrapper，调 restore_images.py + render_mindmap.py |
| `agents/skills/video-to-slides/SKILL.md` | 修改 | ⑤⑥ 步加"必做"；阶段 3 改用 finalize.py |
| `agents/skills/video-summary/SKILL.md` | 修改 | 6.6 节精简 + 引用 reference |
| `agents/skills/video-summary/reference/review_agent_prompt.md` | 新增 | review agent 完整 prompt 模板 |

**职责划分**：
- `restore_images.py` 只做"图片恢复"，单一职责
- `finalize.py` 是 wrapper，串行调两个脚本，agent 唯一入口
- 文档 SKILL.md 描述流程和必做项
- `reference/review_agent_prompt.md` 是 subagent 加载的 prompt 模板

---

### Task 1：删 `restore_images.py` 的 sync_toc

**Files:**
- Modify: `agents/skills/video-to-slides/scripts/restore_images.py:22-77, 119, 130-131, 148-149, 153`
- Modify: `agents/skills/video-to-slides/scripts/restore_images.py:docstring + main()`

**Interfaces:**
- Removes: `extract_toc_from_compact(compact_path) -> str | None`
- Removes: `sync_toc(compact_path, semantic_path) -> bool`
- Modifies: `restore_images(compact_path, semantic_path)` — removes `sync_toc_enabled` param
- Modifies: `main()` — removes `--no-sync-toc` flag

- [ ] **Step 1：写测试 `test_sync_toc_removed`**

创建 `agents/skills/video-to-slides/scripts/tests/test_restore_images_no_sync_toc.py`：

```python
"""验证 restore_images.py 删除了 sync_toc 功能。"""
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'restore_images.py'


def test_sync_toc_function_removed():
    spec = importlib.util.spec_from_file_location('restore_images', SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert not hasattr(mod, 'sync_toc'), \
        'sync_toc 函数应该被删除（目录由 agent 写）'


def test_extract_toc_from_compact_removed():
    spec = importlib.util.spec_from_file_location('restore_images', SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert not hasattr(mod, 'extract_toc_from_compact'), \
        'extract_toc_from_compact 函数应该被删除'


def test_no_sync_toc_argument():
    spec = importlib.util.spec_from_file_location('restore_images', SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    import inspect
    sig = inspect.signature(mod.restore_images)
    assert 'sync_toc_enabled' not in sig.parameters, \
        'restore_images 不应有 sync_toc_enabled 参数'


def test_main_no_no_sync_toc_help():
    """main() 的 usage/help 字符串不应包含 --no-sync-toc。"""
    text = SCRIPT.read_text(encoding='utf-8')
    assert '--no-sync-toc' not in text, \
        'main() usage/help 不应再提到 --no-sync-toc 标志'
```

Run: `cd /Users/jarvis/Documents/VideoToDoc-skills && .venv/bin/pytest .agents/skills/video-to-slides/scripts/tests/test_restore_images_no_sync_toc.py -v`
Expected: **FAIL** — 4 个测试全失败（因为 sync_toc 等函数/参数还在）

- [ ] **Step 2：删 `extract_toc_from_compact` 函数（line 22-37）**

打开 `restore_images.py`，删除 `extract_toc_from_compact` 函数（从 `def extract_toc_from_compact` 到下一个 `def ` 之前的所有行）。

- [ ] **Step 3：删 `sync_toc` 函数（line 40-77）**

删除 `sync_toc` 函数（从 `def sync_toc` 到下一个 `def ` 之前的所有行）。

- [ ] **Step 4：改 `restore_images` 函数签名 + 删 sync_toc 调用**

修改 `restore_images` 函数签名（line 119），去掉 `sync_toc_enabled` 参数：

```python
def restore_images(compact_path: Path, semantic_path: Path) -> Path:
```

删除函数体中的 `if sync_toc_enabled: sync_toc(...)` 调用（line 130-131）。

- [ ] **Step 5：改 `main()` 函数 + 模块 docstring**

修改 `main()`：
- 删除 `--no-sync-toc` 解析（line 148-149）
- 删除 `sync_toc_enabled = "--no-sync-toc" not in args`（line 153）
- 改 `restore_images(compact_path, semantic_path, sync_toc_enabled=sync_toc_enabled)` → `restore_images(compact_path, semantic_path)`

修改 `main()` 的 usage（line 145-147）：
```python
print('用法：python3 restore_images.py <compact_md> <semantic_md>', file=sys.stderr)
```

修改模块 docstring（第 1-9 行附近）—— 删除"默认同时把紧凑版中 ## 图文讲义 与第一个 ### 第 N 页 之间的目录同步到整理版"这句话。

- [ ] **Step 6：跑测试确认通过**

Run: `cd /Users/jarvis/Documents/VideoToDoc-skills && .venv/bin/pytest .agents/skills/video-to-slides/scripts/tests/test_restore_images_no_sync_toc.py -v`
Expected: **PASS** — 4 个测试全过

- [ ] **Step 7：跑回归测试确认未破坏其他功能**

Run: `cd /Users/jarvis/Documents/VideoToDoc-skills && .venv/bin/pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/ -v 2>&1 | tail -50`
Expected: 现有测试全过（如有失败，记录并修复，但不属于本任务范围）

- [ ] **Step 8：Commit**

```bash
cd /Users/jarvis/Documents/VideoToDoc-skills
git add .agents/skills/video-to-slides/scripts/restore_images.py \
        .agents/skills/video-to-slides/scripts/tests/test_restore_images_no_sync_toc.py
git -c user.email="codex@example.com" -c user.name="Codex" \
    commit -m "fix(video-to-slides): 删除 restore_images.py 的 sync_toc 功能"
```

---

### Task 2：写 `finalize.py` wrapper

**Files:**
- Create: `agents/skills/video-to-slides/scripts/finalize.py`
- Create: `agents/skills/video-to-slides/scripts/tests/test_finalize.py`

**Interfaces:**
- `find_compact_and_semantic(run_dir: Path) -> tuple[Path, Path]` — 在 run_dir 下 glob `*_讲义_紧凑版_*.md` 和 `*_讲义_整理版_*.md`
- `run_restore_images(compact_md: Path, semantic_md: Path, project_root: Path) -> None` — subprocess 调 `restore_images.py`
- `run_render_mindmap(run_dir: Path, project_root: Path) -> None` — subprocess 调 `render_mindmap.py`
- `main() -> int` — 入口

- [ ] **Step 1：写测试 `test_find_compact_and_semantic`**

创建 `agents/skills/video-to-slides/scripts/tests/test_finalize.py`：

```python
"""测试 finalize.py wrapper 脚本。"""
import sys
from pathlib import Path

# 把 scripts/ 加到 sys.path 以便导入 finalize
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

import finalize  # noqa: E402


def test_find_compact_and_semantic(tmp_path):
    """glob 找紧凑版和整理版。"""
    (tmp_path / 'video_讲义_紧凑版_20260705.md').write_text('compact')
    (tmp_path / 'video_讲义_整理版_20260705.md').write_text('semantic')
    compact, semantic = finalize.find_compact_and_semantic(tmp_path)
    assert compact.name == 'video_讲义_紧凑版_20260705.md'
    assert semantic.name == 'video_讲义_整理版_20260705.md'


def test_find_compact_and_semantic_missing(tmp_path):
    """缺文件时抛 FileNotFoundError。"""
    import pytest
    with pytest.raises(FileNotFoundError, match='找不到紧凑版'):
        finalize.find_compact_and_semantic(tmp_path)


def test_main_no_args(capsys):
    """main() 无参数时打印 usage 并返回 1。"""
    rc = finalize.main([])
    assert rc == 1
    captured = capsys.readouterr()
    assert '用法：python3 finalize.py' in captured.err


def test_main_nonexistent_run_dir(capsys):
    """run_dir 不存在时返回 2。"""
    rc = finalize.main(['/tmp/nonexistent_run_dir_xyz_finalize_test'])
    assert rc == 2
    captured = capsys.readouterr()
    assert 'run_dir 不存在' in captured.err
```

Run: `cd /Users/jarvis/Documents/VideoToDoc-skills && .venv/bin/pytest .agents/skills/video-to-slides/scripts/tests/test_finalize.py -v`
Expected: **FAIL** — `ModuleNotFoundError: No module named 'finalize'`（脚本还不存在）

- [ ] **Step 2：写 `finalize.py` 框架（不含 subprocess 调用细节）**

创建 `agents/skills/video-to-slides/scripts/finalize.py`：

```python
#!/usr/bin/env python3
"""video-to-slides 阶段 3 收尾 wrapper。

统一执行图片恢复 + 思维导图渲染 + Word 生成。
Agent 不需要分别跑 restore_images.py 和 render_mindmap.py，只跑本脚本即可。

用法：
    python3 finalize.py <run_dir>
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# finalize.py 与 restore_images.py / render_mindmap.py 同处 scripts/ 目录
_SCRIPTS_DIR = Path(__file__).resolve().parent


def find_compact_and_semantic(run_dir: Path) -> tuple[Path, Path]:
    """在 run_dir 下找紧凑版和整理版 Markdown。"""
    compact_candidates = sorted(run_dir.glob('*_讲义_紧凑版_*.md'))
    semantic_candidates = sorted(run_dir.glob('*_讲义_整理版_*.md'))
    if not compact_candidates:
        raise FileNotFoundError(f'run_dir 下找不到紧凑版：{run_dir}')
    if not semantic_candidates:
        raise FileNotFoundError(f'run_dir 下找不到整理版：{run_dir}')
    return compact_candidates[0], semantic_candidates[0]


def run_restore_images(compact_md: Path, semantic_md: Path) -> None:
    """调 restore_images.py 恢复图片（不再同步目录）。"""
    script = _SCRIPTS_DIR / 'restore_images.py'
    # 用当前解释器调用，避免 python3 指向与依赖不匹配的解释器
    subprocess.run([sys.executable, str(script), str(compact_md), str(semantic_md)], check=True)


def run_render_mindmap(run_dir: Path) -> None:
    """调 render_mindmap.py 渲染思维导图 + 生成/刷新两份 Word。"""
    script = _SCRIPTS_DIR / 'render_mindmap.py'
    subprocess.run([sys.executable, str(script), str(run_dir)], check=True)


def main(argv: list[str] | None = None) -> int:
    # argv 显式传入时用之（便于测试），否则读命令行
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print('用法：python3 finalize.py <run_dir>', file=sys.stderr)
        return 1
    run_dir = Path(args[0]).expanduser().resolve()
    if not run_dir.is_dir():
        print(f'❌ run_dir 不存在：{run_dir}', file=sys.stderr)
        return 2

    compact_md, semantic_md = find_compact_and_semantic(run_dir)
    print(f'▶ 恢复图片：{compact_md.name} → {semantic_md.name}', flush=True)
    run_restore_images(compact_md, semantic_md)
    print('▶ 渲染思维导图 + 生成 Word', flush=True)
    run_render_mindmap(run_dir)
    print(f'✅ 收尾完成：{run_dir}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
```

- [ ] **Step 3：跑测试确认通过**

Run: `cd /Users/jarvis/Documents/VideoToDoc-skills && .venv/bin/pytest .agents/skills/video-to-slides/scripts/tests/test_finalize.py -v`
Expected: **PASS** — 4 个测试全过

- [ ] **Step 4：手动跑一次真实 run_dir 验证 wrapper**

找一个已有 run_dir（例如 `runs/【闪客】..._纯语言_20260705_104606/`）：

Run: `cd /Users/jarvis/Documents/VideoToDoc-skills && python3 .agents/skills/video-to-slides/scripts/finalize.py "runs/【闪客】上帝视角拆解三年 LLM 架构演进！_纯语言_20260705_104606" 2>&1 | tail -10`
Expected: 输出 `▶ 恢复图片...` → `▶ 渲染思维导图...` → `✅ 收尾完成...`；没有 traceback；如果图片已被恢复过，再跑一次不会出错（restore_images 是幂等的）

- [ ] **Step 5：Commit**

```bash
cd /Users/jarvis/Documents/VideoToDoc-skills
git add .agents/skills/video-to-slides/scripts/finalize.py \
        .agents/skills/video-to-slides/scripts/tests/test_finalize.py
git -c user.email="codex@example.com" -c user.name="Codex" \
    commit -m "feat(video-to-slides): 新增 finalize.py 阶段 3 收尾 wrapper"
```

---

### Task 3：写 `reference/review_agent_prompt.md`

**Files:**
- Create: `agents/skills/video-summary/reference/review_agent_prompt.md`

**Interfaces:**
- 文档类，无代码接口
- 验证方式：`grep` 检查关键字存在

- [ ] **Step 1：创建 `reference/` 目录（如不存在）**

Run: `mkdir -p /Users/jarvis/Documents/VideoToDoc-skills/.agents/skills/video-summary/reference && ls /Users/jarvis/Documents/VideoToDoc-skills/.agents/skills/video-summary/reference/`
Expected: 目录创建成功，可能为空（创建后无报错）

- [ ] **Step 2：写 prompt 模板（完整内容）**

创建 `agents/skills/video-summary/reference/review_agent_prompt.md`：

```markdown
# review agent 提示词模板

**用途**：video-summary 步骤 6 的 review agent subagent prompt。
**加载方式**：agent 调起 subagent 时，把本文件内容作为 system prompt 传入。

---

你是 video-summary 的独立 review agent（和整理 agent 不同的 context）。
你的任务：复核整理 agent 的合并结果，只输出报告，不直接修改文件。

## 必读文件
- `<run_dir>/merge_input.json`（原始短句 + suggestion 约束）
- `<run_dir>/merged_groups.json`（整理 agent 输出的 456 → N 段合并结果）
- `<run_dir>/merge_review_report.json`（review_merge.py 客观检查初步结果）

## 复核清单（**全做，不可跳项**）

### 1. 句法完整性（最高优先级）
- 相邻段边界是否把"主谓/补语/宾语/状语/程度补语/数量宾语/时间地点状语"拆散？
- 重点检查：段 N 结尾的"X" 和段 N+1 开头的"Y" 是否组成一个被切的完整句子成分
- 触发示例：段 5 结尾"让每个词" + 段 6 开头"都包含其他上下文的信息" → 主谓被切 → critical
- 触发示例：段 7 结尾"让向量间计算点击时" + 段 8 开头"得到一些友好的位置特性" → 状语被切 → critical
- 反例：段末是完整句 + 段首是独立新话题 → 不是 critical

### 2. 同话题聚合
- 同一话题是否被不必要地切到两段？
- 话题切完边界是否自然？

### 3. 每段短句数
- 是否尽量落在 `suggestion.per_group_range` 内？
- 超出范围是否"同话题完整"导致？若是 → 可接受 warning

### 4. 每段字数
- 是否尽量落在 `suggestion.chars_per_group_range` 内？
- 超出范围是否"同话题完整"导致？若是 → 可接受 warning

### 5. 原始短句索引
- 是否连续覆盖 0-N，无跳号、无重复？

## 输出

**覆盖写** `<run_dir>/merge_review_report.json`，结构：

\`\`\`json
{
  "total_groups": 38,
  "issues": [
    {
      "group_index": 5,
      "type": "syntax_break",
      "severity": "critical",
      "description": "段 5 结尾'让每个词'与段 6 开头'都包含其他上下文的信息'是主谓拆分",
      "suggested_fix": "把段 5 的 indices 范围扩到 47-60（让段 6 的'都包含'并入段 5），或反向并入段 6"
    }
  ],
  "pass": false
}
\`\`\`

## 硬规则
- **只输出报告，不直接修改 merged_groups.json**
- 严重性只有 `critical` / `warning` 两级
- `pass` 在所有 issues 都是可接受 warning 时为 true，有 critical 时为 false
- 不要放宽或跳过清单任何一项
```

- [ ] **Step 3：内容验证（grep 检查关键字段）**

Run:
```bash
cd /Users/jarvis/Documents/VideoToDoc-skills
test -f .agents/skills/video-summary/reference/review_agent_prompt.md && echo "✓ 文件存在" || echo "✗ 文件不存在"
grep -c "## 必读文件" .agents/skills/video-summary/reference/review_agent_prompt.md
grep -c "## 复核清单" .agents/skills/video-summary/reference/review_agent_prompt.md
grep -c "### 1. 句法完整性" .agents/skills/video-summary/reference/review_agent_prompt.md
grep -c "### 5. 原始短句索引" .agents/skills/video-summary/reference/review_agent_prompt.md
grep -c "## 硬规则" .agents/skills/video-summary/reference/review_agent_prompt.md
grep -c "只输出报告，不直接修改" .agents/skills/video-summary/reference/review_agent_prompt.md
```
Expected: **全部为非零**（每行 `1` 或更多）—— 文件存在 + 5 个章节标题 + 1 个硬规则关键句

- [ ] **Step 4：Commit**

```bash
cd /Users/jarvis/Documents/VideoToDoc-skills
git add .agents/skills/video-summary/reference/review_agent_prompt.md
git -c user.email="codex@example.com" -c user.name="Codex" \
    commit -m "feat(video-summary): 新增 review_agent_prompt.md 独立 prompt 模板"
```

---

### Task 4：改 `video-to-slides/SKILL.md` ⑤ ⑥ 步

**Files:**
- Modify: `agents/skills/video-to-slides/SKILL.md:170-220`（⑤ 步）
- Modify: `agents/skills/video-to-slides/SKILL.md:196-220`（⑥ 步）

**Interfaces:**
- 文档类，无代码接口
- 验证方式：`grep` + `python -c` 内容关键字检查

- [ ] **Step 1：写内容验证脚本**

创建 `agents/skills/video-to-slides/scripts/tests/check_skill_md_5_6.py`：

```python
"""验证 video-to-slides/SKILL.md ⑤⑥ 步内容更新。"""
import re
import sys
from pathlib import Path

SKILL = Path('/Users/jarvis/Documents/VideoToDoc-skills/.agents/skills/video-to-slides/SKILL.md')
text = SKILL.read_text(encoding='utf-8')


def assert_contains(pattern: str, label: str) -> None:
    assert re.search(pattern, text), f'✗ {label} 不存在：{pattern}'


def assert_not_contains(pattern: str, label: str) -> None:
    assert not re.search(pattern, text), f'✗ {label} 不应存在：{pattern}'


# ⑤ 步必须有"必做，不可跳过"
assert_contains(r'### ⑤ 生成全文目录.*\*\*必做，不可跳过\*\*', '⑤ 步必做标识')

# ⑤ 步必须明确"只写一次到紧凑版"
assert_contains(r'目录\*\*只写一次\*\*到\*\*紧凑版\*\*', '⑤ 步只写一次约束')

# ⑤ 步必须提到"⑥ 步会复制到整理版"
assert_contains(r'⑥ 步会.*复制到整理版', '⑤ 步提示 ⑥ 步复制')

# ⑥ 步必须有"必做，不可跳过"
assert_contains(r'### ⑥ 语义整理.*\*\*必做，不可跳过\*\*', '⑥ 步必做标识')

# ⑥ 步必须包含"从紧凑版复制目录到整理版"任务
assert_contains(r'任务 1：从紧凑版复制目录到整理版', '⑥ 步任务 1')

# ⑥ 步不能再说"改写完成后运行脚本恢复图片并同步目录"
assert_not_contains(r'改写完成后，运行脚本恢复图片并同步目录', '⑥ 步旧描述')

# ⑥ 步不能提到 --no-sync-toc 标志
assert_not_contains(r'--no-sync-toc', '⑥ 步 --no-sync-toc')

print('✓ SKILL.md ⑤⑥ 步内容验证通过')
```

Run: `cd /Users/jarvis/Documents/VideoToDoc-skills && python3 .agents/skills/video-to-slides/scripts/tests/check_skill_md_5_6.py`
Expected: **FAIL** — 多个 assert 失败（因为 SKILL.md 还没改）

- [ ] **Step 2：改写 ⑤ 步**

打开 `agents/skills/video-to-slides/SKILL.md`，定位 `### ⑤ 生成全文目录` 整段（line 170-194），替换为：

````markdown
### ⑤ 生成全文目录（**必做，不可跳过**）

> **Agent 注意**：本步骤是**整个流程中唯一**生成目录的步骤，目录**只写一次**到**紧凑版**；⑥ 步会把它复制到整理版。

**输入**：`<视频标题>_讲义_紧凑版_<时间戳>.md`

**任务**：
1. 阅读紧凑版全文，识别章节划分
2. 在 `## 图文讲义` 标题之后、`### 第 1 页` 之前插入目录

**输出格式**：
```markdown
## 图文讲义

- **第一章 章节名称**（00:00 - 05:30）：简短概述
- **第二章 章节名称**（05:30 - 10:15）：简短概述

---

### 第 1 页 · 00:00 - 00:30
```

**要求**：
- 章节划分依据语义转折，不是按页数均分
- 时间范围精确到秒
- **必须**包含至少 3 个章节项；少于 3 个说明章节切分太粗
````

- [ ] **Step 3：改写 ⑥ 步**

定位 `### ⑥ 语义整理` 整段（line 196-220），替换为：

````markdown
### ⑥ 语义整理（**必做，不可跳过**）

> **Agent 注意**：本步骤包括**复制目录**和**改写文字**两个任务，**两个都必做**。

**输入**：
- `<视频标题>_讲义_整理版_<时间戳>.md`（占位版：每页只有 `<!-- IMAGE:N -->` + 原始 ASR）
- `<视频标题>_讲义_紧凑版_<时间戳>.md`（⑤ 步已写入目录）

**任务**：

#### 任务 1：从紧凑版复制目录到整理版（**先做**）
1. 读紧凑版 `## 图文讲义` 标题后、`### 第 1 页` 之前的内容（即 ⑤ 步写入的目录 + 分隔线）
2. 在整理版的 `## 图文讲义` 标题后（**已有标题，不要再加**）、`### 第 1 页` 之前**插入这段内容**

#### 任务 2：改写每页文字
1. **只改写文字内容**，不要动 `<!-- IMAGE:N -->` 占位符
2. 不新增视频里没有的事实
3. 去掉口播冗余（"好"、"嗯"、"那个"等）
4. 将口语化表达改写为书面语
5. 保留页码和时间信息

**输出**：改写后的 `<视频标题>_讲义_整理版_<时间戳>.md`，**应有 `## 图文讲义` 标题 + 完整目录 + `---` + 各页整理后文字 + 图片占位符**

> ⑥ 步做完后，**不要**单独跑 `restore_images.py`——阶段 3 收尾由 `finalize.py` wrapper 统一处理（见 ⑩ 步）。
````

- [ ] **Step 4：跑验证脚本确认通过**

Run: `cd /Users/jarvis/Documents/VideoToDoc-skills && python3 .agents/skills/video-to-slides/scripts/tests/check_skill_md_5_6.py`
Expected: **PASS** — 输出 `✓ SKILL.md ⑤⑥ 步内容验证通过`

- [ ] **Step 5：Commit**

```bash
cd /Users/jarvis/Documents/VideoToDoc-skills
git add .agents/skills/video-to-slides/SKILL.md \
        .agents/skills/video-to-slides/scripts/tests/check_skill_md_5_6.py
git -c user.email="codex@example.com" -c user.name="Codex" \
    commit -m "docs(video-to-slides): SKILL.md ⑤⑥ 步加必做标识 + ⑥ 步加复制目录任务"
```

---

### Task 5：改 `video-to-slides/SKILL.md` 阶段 3 收尾

**Files:**
- Modify: `agents/skills/video-to-slides/SKILL.md:237-271`（阶段 3 收尾 + ⑧⑨⑩ 步）
- Create: `agents/skills/video-to-slides/scripts/tests/check_skill_md_stage3.py`

- [ ] **Step 1：写内容验证脚本**

创建 `agents/skills/video-to-slides/scripts/tests/check_skill_md_stage3.py`：

```python
"""验证 video-to-slides/SKILL.md 阶段 3 收尾用 finalize.py wrapper。"""
import re
from pathlib import Path

SKILL = Path('/Users/jarvis/Documents/VideoToDoc-skills/.agents/skills/video-to-slides/SKILL.md')
text = SKILL.read_text(encoding='utf-8')


def assert_contains(pattern: str, label: str) -> None:
    assert re.search(pattern, text), f'✗ {label} 不存在：{pattern}'


def assert_not_contains(pattern: str, label: str) -> None:
    assert not re.search(pattern, text), f'✗ {label} 不应存在：{pattern}'


# 必须有阶段 3 描述提到 finalize.py
assert_contains(r'finalize\.py', '阶段 3 收尾提到 finalize.py')

# 必须有"统一入口"或"统一脚本"或类似描述
assert_contains(r'(统一入口|统一脚本|wrapper|不需要分别跑|不需要单独跑)', '阶段 3 wrapper 描述')

# 不应再有单独"### ⑧ 恢复图片并同步目录"或"### ⑨ 渲染导图"作为独立步
assert_not_contains(r'### ⑧ 恢复图片并同步目录', '独立 ⑧ 步')
assert_not_contains(r'### ⑨ 渲染导图', '独立 ⑨ 步')

print('✓ SKILL.md 阶段 3 收尾验证通过')
```

Run: `cd /Users/jarvis/Documents/VideoToDoc-skills && python3 .agents/skills/video-to-slides/scripts/tests/check_skill_md_stage3.py`
Expected: **FAIL** — 旧阶段 3 描述还在，没改

- [ ] **Step 2：改写阶段 3 收尾**

打开 `agents/skills/video-to-slides/SKILL.md`，定位 `## 阶段 3：脚本自动收尾` 整段（line 237-271），替换为：

````markdown
## 阶段 3：脚本自动收尾

> **Agent 注意**：以下步骤由 `finalize.py` **统一脚本**完成，你不需要分别跑多个命令。

### ⑩ 收尾：图片恢复 + 思维导图 + Word

- 运行 `python3 .agents/skills/video-to-slides/scripts/finalize.py <run_dir>`：
  - 自动恢复图片（`restore_images.py`）
  - 自动渲染思维导图（`render_mindmap.py`）
  - 自动生成/刷新紧凑版、整理版两份 Word
- 当节点过多或单图尺寸过大时，自动按章节拆分 `mindmap_01.png`、`mindmap_02.png`... 并同步插入 Markdown/Word
- **此步骤是 agent 唯一需要手动运行的脚本命令**（阶段 1 入口 `process.py` 除外）
````

- [ ] **Step 3：跑验证脚本确认通过**

Run: `cd /Users/jarvis/Documents/VideoToDoc-skills && python3 .agents/skills/video-to-slides/scripts/tests/check_skill_md_stage3.py`
Expected: **PASS** — 输出 `✓ SKILL.md 阶段 3 收尾验证通过`

- [ ] **Step 4：Commit**

```bash
cd /Users/jarvis/Documents/VideoToDoc-skills
git add .agents/skills/video-to-slides/SKILL.md \
        .agents/skills/video-to-slides/scripts/tests/check_skill_md_stage3.py
git -c user.email="codex@example.com" -c user.name="Codex" \
    commit -m "docs(video-to-slides): 阶段 3 收尾改用 finalize.py wrapper"
```

---

### Task 6：改 `video-summary/SKILL.md` 6.6 节

**Files:**
- Modify: `agents/skills/video-summary/SKILL.md:134-178`（6.6 节）
- Create: `agents/skills/video-summary/scripts/tests/check_skill_md_6_6.py`

- [ ] **Step 1：写内容验证脚本**

创建 `agents/skills/video-summary/scripts/tests/check_skill_md_6_6.py`：

```python
"""验证 video-summary/SKILL.md 6.6 节精简 + 引用 reference。"""
import re
from pathlib import Path

SKILL = Path('/Users/jarvis/Documents/VideoToDoc-skills/.agents/skills/video-summary/SKILL.md')
text = SKILL.read_text(encoding='utf-8')


def assert_contains(pattern: str, label: str) -> None:
    assert re.search(pattern, text), f'✗ {label} 不存在：{pattern}'


def assert_not_contains(pattern: str, label: str) -> None:
    assert not re.search(pattern, text), f'✗ {label} 不应存在：{pattern}'


# 6.6 节必须有"必做，不可跳过"
assert_contains(r'### 6\.6 Review Agent.*\*\*必做，不可跳过\*\*', '6.6 节必做标识')

# 6.6 节不应有"为什么强制"段（按用户原则删掉）
assert_not_contains(r'## 为什么强制', '6.6 节"为什么强制"段')

# 6.6 节不应再内联旧版复核清单（句法完整性等应移到 reference）
assert_not_contains(r'相邻段边界是否把补语/数据/宾语拆散', '旧 6.6 内联清单')

# 6.6 节应引用 reference/review_agent_prompt.md
assert_contains(r'reference/review_agent_prompt\.md', '6.6 节引用 reference')

# 6.6 节应有"review agent 规则"小节
assert_contains(r'review agent 规则', '6.6 节规则小节')

# 6.6 节不应内联完整 prompt 模板（应只指向 reference）
# 检测：内联模板里有"复核清单"完整 5 项（如果内联会全出现）
inline_template_count = text.count('### 1. 句法完整性')
assert inline_template_count == 0, \
    f'✗ 6.6 节不应内联 prompt 模板（发现 {inline_template_count} 处"句法完整性"），应指向 reference/'

print('✓ SKILL.md 6.6 节验证通过')
```

Run: `cd /Users/jarvis/Documents/VideoToDoc-skills && python3 .agents/skills/video-summary/scripts/tests/check_skill_md_6_6.py`
Expected: **FAIL** — 旧 6.6 节还在（"背景"段、内联复核清单、无"必做"标识）

- [ ] **Step 2：改写 6.6 节**

打开 `agents/skills/video-summary/SKILL.md`，定位 `### 6.6 Review Agent 复核合并质量` 整段（line 134-178），替换为：

````markdown
### 6.6 Review Agent 复核合并质量（**必做，不可跳过**）

> ⚠️ **警告**：本步骤**必须**独立 subagent 跑一次，**不跑不许进入下一步**（摘要 / video-to-slides / feishu 发布）。

**步骤**：

1. 整理 agent 完成首次合并 → `merged_groups.json`
2. 跑 `apply_merge.py` 校验索引连续 → `transcript_merged.json`
3. 跑 `review_merge.py` 客观检查 → 初步 `merge_review_report.json`
4. **【必做】派独立 subagent 复核**：使用 `reference/review_agent_prompt.md` 中的 prompt 模板
5. subagent 读 `merge_input.json` + `merged_groups.json` + `merge_review_report.json`，输出增强版 `merge_review_report.json`
6. 整理 agent 根据 critical issues **局部修正** `merged_groups.json`
7. 重跑 `apply_merge.py` + `review_merge.py` + subagent 复核，直到 `pass=true`
8. **直到 pass 才进下一步**

**review agent 规则**：
- 只输出报告，不直接修改 `merged_groups.json`。
- critical 问题必须标记；warning 问题允许整理 agent 酌情处理。
- 所有判断必须基于 `merge_input.json` 中的约束数据，不能自行放宽。
- 遇到超出 `chars_per_group_range` 或 `per_group_range` 的段，先判断是否为"同话题完整"导致；若是，可接受为 warning；若不是，应建议切分。

**Prompt 模板**：见 `reference/review_agent_prompt.md`（独立文件，agent 调起 subagent 时加载）。
````

- [ ] **Step 3：跑验证脚本确认通过**

Run: `cd /Users/jarvis/Documents/VideoToDoc-skills && python3 .agents/skills/video-summary/scripts/tests/check_skill_md_6_6.py`
Expected: **PASS** — 输出 `✓ SKILL.md 6.6 节验证通过`

- [ ] **Step 4：Commit**

```bash
cd /Users/jarvis/Documents/VideoToDoc-skills
git add .agents/skills/video-summary/SKILL.md \
        .agents/skills/video-summary/scripts/tests/check_skill_md_6_6.py
git -c user.email="codex@example.com" -c user.name="Codex" \
    commit -m "docs(video-summary): 6.6 节精简 + 引用 reference"
```

---

### Task 7：端到端验收测试

**Files:**
- 无文件修改
- 验证：重跑一次完整 video-summary + video-to-slides 流程

- [ ] **Step 1：删除 A 目录的占位整理版（避免干扰）**

Run: `cd /Users/jarvis/Documents/VideoToDoc-skills && ls "runs/【闪客】上帝视角拆解三年 LLM 架构演进！_纯语言_20260705_104606/"`
Expected: 列出 A 目录文件，准备作为验收测试输入

- [ ] **Step 2：手动重跑 A 目录流程（端到端验证）**

流程：
1. 用一个**测试 agent**（或手动）模拟：
   - 在 A 目录的紧凑版 `## 图文讲义` 后插入目录（⑤ 步）
   - 在 A 目录的整理版 `## 图文讲义` 后插入目录（⑥ 步任务 1）
   - ⑥ 步任务 2 改写文字（如果有差异）
2. 跑 `python3 .agents/skills/video-to-slides/scripts/finalize.py <A 目录>`
3. 检查整理版：
   - `## 图文讲义` 标题 + 目录 + `---` + 各页 ✓
   - 图片被恢复（`<!-- IMAGE:N -->` → `![第 N 页](path)`）✓
   - 没有 sync_toc 误生成的"第 1 页重复" ✓

Run: `cd /Users/jarvis/Documents/VideoToDoc-skills && python3 .agents/skills/video-to-slides/scripts/finalize.py "runs/【闪客】上帝视角拆解三年 LLM 架构演进！_纯语言_20260705_104606" 2>&1 | tail -10`
Expected: 成功执行，输出 `▶ 恢复图片...` → `▶ 渲染思维导图...` → `✅ 收尾完成...`

- [ ] **Step 3：验证整理版内容正确**

Run: `grep -c "^### 第 1 页" "/Users/jarvis/Documents/VideoToDoc-skills/runs/【闪客】上帝视角拆解三年 LLM 架构演进！_纯语言_20260705_104606/【闪客】上帝视角拆解三年 LLM 架构演进！_纯语言_讲义_整理版_20260705_105650.md"`
Expected: 输出 `1`（`### 第 1 页` 仅出现 1 次；若为 2 说明 sync_toc 残留未清）

Run: `head -20 "/Users/jarvis/Documents/VideoToDoc-skills/runs/【闪客】上帝视角拆解三年 LLM 架构演进！_纯语言_20260705_104606/【闪客】上帝视角拆解三年 LLM 架构演进！_纯语言_讲义_整理版_20260705_105650.md"`
Expected: 第 1 行是 H1；第 2 行是空行；后面是 `## 图文讲义` 标题（不是 `### 第 1 页` 直接开始）

- [ ] **Step 4：跑所有相关测试**

Run:
```bash
cd /Users/jarvis/Documents/VideoToDoc-skills
.venv/bin/pytest .agents/skills/video-to-slides/scripts/tests/test_restore_images_no_sync_toc.py -v
.venv/bin/pytest .agents/skills/video-to-slides/scripts/tests/test_finalize.py -v
python3 .agents/skills/video-to-slides/scripts/tests/check_skill_md_5_6.py
python3 .agents/skills/video-to-slides/scripts/tests/check_skill_md_stage3.py
python3 .agents/skills/video-summary/scripts/tests/check_skill_md_6_6.py
```
Expected: **全部 PASS**

- [ ] **Step 5：跑 video-to-slides 现有测试套件确认未破坏**

Run: `cd /Users/jarvis/Documents/VideoToDoc-skills && .venv/bin/pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/ -v 2>&1 | tail -20`
Expected: 现有测试全过（或已记录的失败与本次修复无关）

- [ ] **Step 6：Final commit（如有需要）**

如果 Task 7 验证中发现需要小调整，按需 commit。否则无 commit。

---

## 测试验收总表（明确结果和案例）

| # | 测试名 | 文件 | 验收命令 | 预期结果 |
|---|---|---|---|---|
| 1 | `test_sync_toc_function_removed` | `tests/test_restore_images_no_sync_toc.py` | `pytest -v` | FAIL → 删后 PASS |
| 2 | `test_extract_toc_from_compact_removed` | 同上 | 同上 | FAIL → 删后 PASS |
| 3 | `test_no_sync_toc_argument` | 同上 | 同上 | FAIL → 改签名后 PASS |
| 4 | `test_main_no_no_sync_toc_help` | 同上 | `grep` 验证 | FAIL → 删文档后 PASS |
| 5 | `test_find_compact_and_semantic` | `tests/test_finalize.py` | `pytest -v` | FAIL → 实现后 PASS |
| 6 | `test_find_compact_and_semantic_missing` | 同上 | 同上 | FAIL → 实现后 PASS |
| 7 | `test_main_no_args` | 同上 | 同上 | FAIL → 实现后 PASS |
| 8 | `test_main_nonexistent_run_dir` | 同上 | 同上 | FAIL → 实现后 PASS |
| 9 | finalize.py 真实 run_dir 验证 | 手动 | `python3 finalize.py <run_dir>` | 输出 `✅ 收尾完成` |
| 10 | review_agent_prompt.md 内容验证 | `reference/` | `grep -c "## 必读文件"` | `1` |
| 11 | review_agent_prompt.md 内容验证 | 同上 | `grep -c "## 复核清单"` | `1` |
| 12 | review_agent_prompt.md 内容验证 | 同上 | `grep -c "### 1. 句法完整性"` | `1` |
| 13 | review_agent_prompt.md 内容验证 | 同上 | `grep -c "## 硬规则"` | `1` |
| 14 | SKILL.md ⑤ ⑥ 步内容验证 | `tests/check_skill_md_5_6.py` | `python3 check_skill_md_5_6.py` | FAIL → 改后 PASS |
| 15 | SKILL.md 阶段 3 内容验证 | `tests/check_skill_md_stage3.py` | `python3 check_skill_md_stage3.py` | FAIL → 改后 PASS |
| 16 | SKILL.md 6.6 节内容验证 | `tests/check_skill_md_6_6.py` | `python3 check_skill_md_6_6.py` | FAIL → 改后 PASS |
| 17 | 端到端：整理版 `### 第 1 页` 出现次数 | 手动 | `grep -c "^### 第 1 页" <整理版>` | `<=2`（旧版是 2，新版是 1） |
| 18 | 端到端：整理版有 `## 图文讲义` 标题 | 手动 | `head -10 <整理版> \| grep "## 图文讲义"` | 输出包含 `## 图文讲义` |
| 19 | 回归：video-to-slides 现有测试 | 手动 | `pytest videotodoc/tests/ -v` | 全过 |

**每个测试的输入/输出明确**：
- 测试 1-4：跑 `pytest` 命令，验证 sync_toc 等函数/参数被删除
- 测试 5-8：跑 `pytest` 命令，验证 finalize.py 函数行为
- 测试 9：手动跑 `finalize.py`，验证端到端执行成功
- 测试 10-13：跑 `grep` 命令，验证 prompt 模板关键字段存在
- 测试 14-16：跑 Python 验证脚本，验证 SKILL.md 改动覆盖所有断言
- 测试 17-18：跑 `grep` 命令，验证整理版结构正确
- 测试 19：跑 `pytest` 命令，验证未破坏现有功能

---

## 执行交接

计划已完成并保存到 `docs/superpowers/plans/2026-07-05-merge-quality-fixes.md`。

**两种执行方式**：

1. **子代理驱动（推荐）** - 每个任务调度一个新的子代理，任务间进行审查，快速迭代
2. **内联执行** - 在当前会话中使用 executing-plans 执行任务，批量执行并设有检查点

**选哪种方式？**
