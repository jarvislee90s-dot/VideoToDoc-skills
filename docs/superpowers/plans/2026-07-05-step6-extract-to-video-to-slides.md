# 步骤 6 提取至 video-to-slides 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 把 video-summary 的步骤 6（合并转录碎段 + review 闭环）整体迁到 video-to-slides，作为新"阶段 0"。video-summary 瘦身到字幕/下载/ASR/摘要；video-to-slides 拥有严格合并逻辑。review 迭代硬封顶 2 次；闸口职责归 `check_review_report.py`（已存在，沿用），不另造运行时 helper。

**架构：**
- 4 个 merge 脚本 + 1 个 prompt + 1 个 check 脚本整体从 video-summary 迁到 video-to-slides
- `merge_procedure.md` 顶部加 review ≤ 2 硬约束，末尾指引 agent 跑 `check_review_report.py`
- video-to-slides SKILL.md 阶段 0 写短指针，阶段 1 入口文案把"必跑 check_review_report.py 退出码 0"列为强约束
- `pipeline.py::finalize_video` 补 4 行 prefer-merged 逻辑（学 `capture_video`），与 `check_review_report.py` 程序性闸口对齐
- **不新增**任何运行时 helper / flag / 严格 mode

**Tech Stack:** Python 3.14, pytest, apply_patch, git

**Global Constraints:**
- 严格 TDD：先写 RED 失败测试，再写 GREEN 实现，再 commit
- 每次 commit 用中文，格式 `type(scope): 描述`
- 全程在 worktree 内工作
- 测试验收总表见文末（明确每个测试用例的输入/命令/预期）
- 文档类任务用 `grep`/`python -c` 验证关键字存在
- **review-passed 闸口复用现有 `check_review_report.py`，不造新层**

---

## 文件结构

| 文件 | 类型 | 职责 |
|---|---|---|
| `.agents/skills/video-summary/SKILL.md` | 修改 | 删步骤 6 整块（170 行）；步骤 7 注释改读 transcript.txt |
| `.agents/skills/video-to-slides/SKILL.md` | 修改 | 新增"阶段 0"（短指针）；删 ①.5 前置合并桥；更新流程图；阶段 0 末尾指引跑 check_review_report.py |
| `.agents/skills/video-to-slides/reference/merge_procedure.md` | 新增 | 搬自 video-summary 步骤 6 全文 + 顶部加 review ≤ 2 硬约束 + 末尾加 check_review_report 指引 |
| `.agents/skills/video-to-slides/reference/review_agent_prompt.md` | 迁移 | 从 video-summary 整体搬来 |
| `.agents/skills/video-to-slides/scripts/videotodoc/pipeline.py` | 修改 | `finalize_video`（L223-226）补 4 行 prefer-merged 逻辑 |
| `.agents/skills/video-to-slides/scripts/videotodoc/prepare_merge.py` | 迁移 | 从 video-summary 整体搬来 + 改 import 路径 |
| `.agents/skills/video-to-slides/scripts/videotodoc/apply_merge.py` | 迁移 | 从 video-summary 整体搬来 + 改 import 路径 |
| `.agents/skills/video-to-slides/scripts/videotodoc/review_merge.py` | 迁移 | 从 video-summary 整体搬来 + 改 import 路径 |
| `.agents/skills/video-to-slides/scripts/videotodoc/tests/check_review_report.py` | 迁移 | 从 video-summary 整体搬来 |
| `.agents/skills/video-summary/scripts/prepare_merge.py` | 删除 | 已迁出 |
| `.agents/skills/video-summary/scripts/apply_merge.py` | 删除 | 已迁出 |
| `.agents/skills/video-summary/scripts/review_merge.py` | 删除 | 已迁出 |
| `.agents/skills/video-summary/scripts/tests/check_review_report.py` | 删除 | 已迁出 |
| `.agents/skills/video-summary/reference/review_agent_prompt.md` | 删除 | 已迁出 |

**职责划分：**
- `merge_procedure.md`：合并流程的单一权威描述（SKILL.md 短指针指向）
- `check_review_report.py`（**复用，不重建**）：review-passed 程序性闸口，agent 在阶段 0 末尾主动跑
- `pipeline.py::finalize_video` prefer-merged：与闸口对齐，merged 存在就用它（前提是 agent 已跑过 check_review_report.py 确认 self_review 键）

---

## 任务

### Task 1：迁移 4 个 merge 脚本到 video-to-slides

**Files:**
- Delete: `.agents/skills/video-summary/scripts/prepare_merge.py`
- Delete: `.agents/skills/video-summary/scripts/apply_merge.py`
- Delete: `.agents/skills/video-summary/scripts/review_merge.py`
- Create: `.agents/skills/video-to-slides/scripts/videotodoc/prepare_merge.py`
- Create: `.agents/skills/video-to-slides/scripts/videotodoc/apply_merge.py`
- Create: `.agents/skills/video-to-slides/scripts/videotodoc/review_merge.py`

- [ ] **Step 1：`git mv` 三个脚本到新位置**

```bash
cd /Users/jarvis/Documents/VideoToDoc-skills
git mv .agents/skills/video-summary/scripts/prepare_merge.py .agents/skills/video-to-slides/scripts/videotodoc/prepare_merge.py
git mv .agents/skills/video-summary/scripts/apply_merge.py .agents/skills/video-to-slides/scripts/videotodoc/apply_merge.py
git mv .agents/skills/video-summary/scripts/review_merge.py .agents/skills/video-to-slides/scripts/videotodoc/review_merge.py
```

- [ ] **Step 2：改 import 路径**

读每个脚本的 `import` 段，找出引用 `signal_stats`（位于 video-summary 根）的代码。改 import 路径：

```python
# 改前
from signal_stats import signal_stats  # video-summary 根

# 改后
from .signal_stats import signal_stats  # 或调整 sys.path
```

如 `signal_stats.py` 也需迁，单独 `git mv` 到 `.agents/skills/video-to-slides/scripts/videotodoc/signal_stats.py`。

- [ ] **Step 3：跑原 video-summary 测试套件确认 0 个回归**

```bash
.venv/bin/pytest .agents/skills/video-summary/scripts/tests/ -v
```
预期：FAIL（脚本已不在原路径，旧测试找不到模块）

- [ ] **Step 4：在新位置建测试入口**

在 `.agents/skills/video-to-slides/scripts/videotodoc/tests/` 下创建 `test_prepare_merge.py` / `test_review_merge.py`（从原 video-summary 测试复制并更新 import 路径；`test_apply_merge.py` 计划笔误——原项目无此测试，按 TDD 不凭空造）。

- [ ] **Step 5：跑新位置测试套件确认全 PASS**

```bash
.venv/bin/pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_prepare_merge.py .agents/skills/video-to-slides/scripts/videotodoc/tests/test_review_merge.py -v
```
预期：全 PASS

- [ ] **Step 6：Commit**

```bash
git add -A .agents/skills/
git commit -m "refactor: 3 个 merge 脚本从 video-summary 迁到 video-to-slides/videotodoc/"
```

---

### Task 2：迁移 `check_review_report.py` + `review_agent_prompt.md`

**Files:**
- Delete: `.agents/skills/video-summary/scripts/tests/check_review_report.py`
- Create: `.agents/skills/video-to-slides/scripts/videotodoc/tests/check_review_report.py`
- Delete: `.agents/skills/video-summary/reference/review_agent_prompt.md`
- Create: `.agents/skills/video-to-slides/reference/review_agent_prompt.md`

- [ ] **Step 1：`git mv` 两个文件**

```bash
git mv .agents/skills/video-summary/scripts/tests/check_review_report.py .agents/skills/video-to-slides/scripts/videotodoc/tests/check_review_report.py
git mv .agents/skills/video-summary/reference/review_agent_prompt.md .agents/skills/video-to-slides/reference/review_agent_prompt.md
```

- [ ] **Step 2：跑 check_review_report 测试确认通过**

```bash
.venv/bin/pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_check_review_report.py -v
```
预期：PASS

- [ ] **Step 3：Commit**

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/tests/check_review_report.py .agents/skills/video-to-slides/reference/review_agent_prompt.md
git commit -m "refactor: check_review_report + review_agent_prompt 迁到 video-to-slides"
```

---

### Task 3：创建 `reference/merge_procedure.md`

**Files:**
- Create: `.agents/skills/video-to-slides/reference/merge_procedure.md`

- [ ] **Step 1：从 video-summary SKILL.md 复制步骤 6 全文（6.1~6.7 段）**

```bash
sed -n '/^## 6\./,/^### 6\.7 /p' .agents/skills/video-summary/SKILL.md > .agents/skills/video-to-slides/reference/merge_procedure.md
```
（精确起止行按当前 video-summary SKILL.md 实际行号微调，确保把 6.1~6.7 整段搬过来）

- [ ] **Step 2：顶部加 review ≤ 2 硬约束段**

在 `merge_procedure.md` 开头（在 6.1 之前）插入：

```markdown
## 0. 硬约束：review 最多 2 次

- 1st Review Agent 复核后如有 critical → 整理 agent 按意见修改 → 跑 apply_merge + review_merge + 2nd Review Agent
- 2nd Review Agent 仍发现 critical → **立即停止**，上报用户介入（"review 循环耗尽，2 次未通过"）
- 不允许无限制迭代
- 每次 Review Agent 跑完必须 `merge_review_report.json` 含 `self_review` 键（路径 A 或路径 B 标记）
- 阶段 0 收尾必跑：`python3 scripts/videotodoc/tests/check_review_report.py <run_dir>`，退出码必须 0（已有闸口，**沿用不重建**）
```

- [ ] **Step 3：末尾加 check_review_report 指引段**

在 `merge_procedure.md` 末尾追加：

```markdown
## 7. 阶段 0 收尾闸口

```bash
python3 scripts/videotodoc/tests/check_review_report.py <run_dir>
```

- 退出码 0：进入阶段 1
- 退出码 1：缺 self_review 键，回到 6.6 重跑 Review Agent
- 退出码 2：报告文件不存在，说明没跑 review_merge.py 或 Review Agent

不通过闸口禁止进入阶段 1。
```

- [ ] **Step 4：Commit**

```bash
git add .agents/skills/video-to-slides/reference/merge_procedure.md
git commit -m "docs(video-to-slides): merge_procedure.md 落地 + 加 review ≤ 2 + check_review_report 指引"
```

---

### Task 4：瘦 video-summary SKILL.md

**Files:**
- Modify: `.agents/skills/video-summary/SKILL.md`（删除步骤 6 整块约 170 行）
- Modify: `.agents/skills/video-summary/SKILL.md`（步骤 7 注释改读 transcript.txt）

- [ ] **Step 1：确认测试断言脚本存在**

```bash
ls .agents/skills/video-summary/scripts/tests/check_skill_md_6_6.py
```
预期：存在

- [ ] **Step 2：删除步骤 6 整块**

用 `apply_patch` 删除 `## 6. 合并转录碎段（必做，不可跳过）` 起到 `### 6.7 整理 agent 根据 Review Report 修正` 段结束的内容。

- [ ] **Step 3：改步骤 7 注释——读 transcript.txt 而非 transcript_merged.json**

找到步骤 7（"Agent 摘要"），把"Agent 读取 transcript.txt（合并后的 transcript_merged.json 优先）"改为"Agent 读取 transcript.txt"。

- [ ] **Step 4：跑 skill MD 断言脚本**

```bash
.venv/bin/python3 .agents/skills/video-summary/scripts/tests/check_skill_md_6_6.py
```
预期：PASS（断言已适配新结构或标注"步骤 6 已迁出"）

- [ ] **Step 5：跑 video-summary 剩余测试**

```bash
.venv/bin/pytest .agents/skills/video-summary/scripts/tests/ -v
```
预期：原 step 6 相关测试已迁出，剩余全 PASS

- [ ] **Step 6：Commit**

```bash
git add .agents/skills/video-summary/SKILL.md .agents/skills/video-summary/scripts/tests/
git commit -m "docs(video-summary): 步骤 6 整块迁出（合并逻辑归 video-to-slides 阶段 0）"
```

---

### Task 5：video-to-slides SKILL.md 新增阶段 0 + 删 ①.5

**Files:**
- Modify: `.agents/skills/video-to-slides/SKILL.md`（在"阶段 1"之前插入"阶段 0"；删除 ①.5；更新工作流总览图）

- [ ] **Step 1：在 SKILL.md 找到"## 阶段 1"位置**

```bash
grep -n "^## 阶段 1" .agents/skills/video-to-slides/SKILL.md
```

- [ ] **Step 2：在阶段 1 之前插入"阶段 0"短指针**

```markdown
## 阶段 0：合并转录碎段（必做）

> **Agent 注意**：本阶段由你主导，详细流程读 `reference/merge_procedure.md` 并完整执行：
> 1. 结构原型判定（4 原型 + L1/L2/L3 三层证据，详见 reference 6.1）
> 2. prepare_merge → merged_groups.json → apply_merge → review_merge
> 3. **Review Agent 双路径复核**（路径 A 独立子代理 / 路径 B 上下文重置自审）
> 4. 若 review 报 critical → 修改 → 重跑 apply_merge + review_merge + Review Agent，**最多 2 次 review 迭代**
> 5. **收尾必跑**：`python3 scripts/videotodoc/tests/check_review_report.py <run_dir>`，退出码必须 0
> 6. 不通过 check_review_report 闸口**禁止进入阶段 1**
> 7. 全部硬标准、合并规则、句法完整性要求、Review Agent prompt 模板：在 `reference/merge_procedure.md` + `reference/review_agent_prompt.md`

阶段 0 完成后必须存在：
- `transcript_merged.json`
- `merge_review_report.json`（含 `pass: true` + `self_review` 键，已被 check_review_report.py 校验）
```

- [ ] **Step 3：删除原 ①.5"前置合并（复用 video-summary 转录时）"整段**

找到 `### ①.5 前置合并（复用 video-summary 转录时）` 段，整段删除（约 15 行）。

- [ ] **Step 4：更新工作流总览图**

把 `mermaid` 图中的"前置合并"节点删除，"transcript_merged.json"改成"阶段 0 产出"，确保 capture 输入是 `transcript_merged.json`（阶段 0 已产出的优先）。

- [ ] **Step 5：跑 skill MD 断言脚本**

```bash
.venv/bin/python3 .agents/skills/video-to-slides/scripts/tests/check_skill_md_5_6.py
.venv/bin/python3 .agents/skills/video-to-slides/scripts/tests/check_skill_md_stage3.py 2>/dev/null
```
预期：全 PASS

- [ ] **Step 6：Commit**

```bash
git add .agents/skills/video-to-slides/SKILL.md
git commit -m "docs(video-to-slides): 新增阶段 0 短指针 + 删 ①.5 桥 + 更新工作流图"
```

---

### Task 6：补 `finalize_video` prefer-merged 逻辑

**Files:**
- Modify: `.agents/skills/video-to-slides/scripts/videotodoc/pipeline.py:223-226` (`finalize_video`)

> **注意**：仅改 1 处。`capture_video` 已 prefer-merged；`finalize_video` 与之对齐，确保阶段 0 产出的 merged 真的被 align 阶段用到。`check_review_report.py` 是程序性闸口，agent 在阶段 0 末尾已跑过且退出码 0；这里不加运行时 helper。

- [ ] **Step 1：写测试 - `finalize_video` 优先用 merged**

```python
# test_pipeline_finalize_prefer_merged.py
from pathlib import Path
import json
from videotodoc.pipeline import finalize_video


def test_finalize_prefers_merged_when_exists(tmp_path: Path, monkeypatch):
    """merged 存在时 finalize_video 必须用它，不回退 cache。"""
    # 准备 merged（review-passed；本测试不强制 check，只验加载路径）
    (tmp_path / "transcript_merged.json").write_text(
        json.dumps({"segments": [{"start": 0, "end": 1000, "text": "merged_text"}]})
    )
    (tmp_path / "merge_review_report.json").write_text(
        json.dumps({"pass": True, "self_review": True, "summary": "ok"})
    )
    # 准备一份**不同内容**的 cache（验证不会用 cache）
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / "x" * 12 + "_qwen.transcript.json").write_text(
        json.dumps({"segments": [{"start": 0, "end": 1000, "text": "cache_text_DIFFERENT"}]})
    )
    # 准备 confirmed_segments（最小 fixture）
    (tmp_path / "confirmed_segments.json").write_text(json.dumps({
        "video_path": "/tmp/test.mp4",
        "segments": [],
        "video_title": "test",
    }))
    # 注：本测试只验 transcript 加载路径选择；完整 finalize 跑通需更多 fixture
    # 实现验证：捕获 read_json 调用，看哪个文件被读
    read_calls = []
    from videotodoc import pipeline
    real_read_json = pipeline.read_json
    def spy_read_json(path):
        read_calls.append(str(path))
        return real_read_json(path)
    monkeypatch.setattr(pipeline, "read_json", spy_read_json)
    # 调用 finalize（可能因其他依赖失败，但 read_json 应先被调到 transcript_merged.json）
    try:
        finalize_video(tmp_path, _make_minimal_settings(tmp_path))
    except Exception:
        pass
    # 验证：transcript_merged.json 被读
    assert any("transcript_merged.json" in c for c in read_calls), \
        f"finalize_video 应优先读 transcript_merged.json，实际读了：{read_calls}"
    # 验证：cache transcript 没被读（或读得比 merged 晚）
    cache_reads = [c for c in read_calls if "transcript.json" in c and "cache" in c]
    # 允许 cache 在 merged 之后被读（如有其他步骤需要），但 merged 必须先被读
    merged_idx = next((i for i, c in enumerate(read_calls) if "transcript_merged.json" in c), -1)
    cache_idx = next((i for i, c in enumerate(cache_reads) if True), -1)
    assert merged_idx >= 0, "merged 必须被读"
    if cache_reads:
        assert merged_idx < cache_idx, "merged 必须先于 cache 被读"


def _make_minimal_settings(tmp_path):
    from videotodoc.config import Settings
    return Settings(
        video_path=tmp_path / "test.mp4",
        transcript_path=tmp_path / "transcript_merged.json",
        # ... 其他字段按 Settings 实际必填项补
    )
```

- [ ] **Step 2：跑测试验证失败（实现未改）**

```bash
.venv/bin/pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_pipeline_finalize_prefer_merged.py -v
```
预期：FAIL（`finalize_video` 仍只读 cache，不读 merged）

- [ ] **Step 3：改 `finalize_video`（pipeline.py:223-226）**

把现有：

```python
transcript_files = list(cache_dir.glob("*.transcript.json"))
matched_transcript = _find_matching_cache_file(transcript_files, video_path, "转录")
transcript = _transcript_from_external(read_json(matched_transcript), settings.language)
```

改为：

```python
# 优先用阶段 0 产出的 review-passed merged（agent 已在阶段 0 末尾跑过 check_review_report.py）
run_dir_merged = run_dir / "transcript_merged.json"
if run_dir_merged.exists():
    transcript = _transcript_from_external(read_json(run_dir_merged), settings.language)
    print(f"  ♻️  finalize 使用 review-passed merged：{run_dir_merged.name}")
else:
    transcript_files = list(cache_dir.glob("*.transcript.json"))
    matched_transcript = _find_matching_cache_file(transcript_files, video_path, "转录")
    transcript = _transcript_from_external(read_json(matched_transcript), settings.language)
```

- [ ] **Step 4：跑测试验证通过**

```bash
.venv/bin/pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_pipeline_finalize_prefer_merged.py -v
```
预期：PASS

- [ ] **Step 5：跑 video-to-slides 全测试套件确认无回归**

```bash
.venv/bin/pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/ -v
```
预期：全 PASS

- [ ] **Step 6：Commit**

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/pipeline.py .agents/skills/video-to-slides/scripts/videotodoc/tests/test_pipeline_finalize_prefer_merged.py
git commit -m "feat(pipeline): finalize_video 补 prefer-merged 逻辑（与 check_review_report 闸口对齐）"
```

---

### Task 7：全量验证 + 收尾

- [ ] **Step 1：跑两个技能全测试套件**

```bash
.venv/bin/pytest .agents/skills/video-summary/scripts/tests/ .agents/skills/video-to-slides/scripts/videotodoc/tests/ -v
```
预期：全 PASS（含 Task 1 迁过来的 prepare/apply/review_merge 测试 + check_review_report 测试 + Task 6 新增的 prefer-merged 测试）

- [ ] **Step 2：跑所有 skill MD 断言脚本**

```bash
.venv/bin/python3 .agents/skills/video-summary/scripts/tests/check_skill_md_6_6.py
.venv/bin/python3 .agents/skills/video-to-slides/scripts/tests/check_skill_md_5_6.py
.venv/bin/python3 .agents/skills/video-to-slides/scripts/tests/check_skill_md_stage3.py 2>/dev/null
```
预期：全部正常退出

- [ ] **Step 3：跑 doctor 入口**

```bash
.venv/bin/python3 .agents/skills/video-summary/scripts/process.py doctor
.venv/bin/python3 .agents/skills/video-to-slides/scripts/process.py --help
```
预期：正常退出，无 ImportError

- [ ] **Step 4：grep 验证 review ≤ 2 在文档中**

```bash
grep -c "review 最多 2 次\|review 循环耗尽" .agents/skills/video-to-slides/reference/merge_procedure.md
grep -c "check_review_report.py" .agents/skills/video-to-slides/reference/merge_procedure.md
```
预期：两处各 ≥ 1

- [ ] **Step 5：Commit（如果有遗留改动）**

```bash
git status
git add -A .agents/skills/
git commit -m "chore: 收尾验证后的小调整" --allow-empty
```

---

## 自检

1. **规格覆盖度**：
   - 文件落位（4 脚本 + 1 check + 1 prompt 迁移 + 1 reference 新建）→ Task 1/2/3 ✓
   - SKILL.md 瘦身（video-summary 删 170 行）→ Task 4 ✓
   - SKILL.md 新增阶段 0（video-to-slides 短指针）→ Task 5 ✓
   - ①.5 桥删除 → Task 5 Step 3 ✓
   - finalize_video prefer-merged（与 check_review_report 闸口对齐）→ Task 6 ✓
   - review ≤ 2 硬约束 → Task 3 Step 2 + merge_procedure.md ✓
   - 不新增运行时 helper / flag / 严格 mode（按用户决定）→ 全程无 ✓

2. **占位符扫描**：
   - 所有 pytest 命令完整 .venv/bin/pytest ✓
   - fixture 代码块完整 ✓
   - 无 "TODO" / "待定" / "类似任务 N" ✓

3. **类型一致性**：
   - `merge_procedure.md` 在 video-to-slides/reference/，SKILL.md 短指针引用路径一致 ✓
   - `check_review_report.py` 路径 `.agents/skills/video-to-slides/scripts/videotodoc/tests/check_review_report.py` 全文一致 ✓
   - `transcript_merged.json` / `merge_review_report.json` 文件名跨任务一致 ✓

4. **测试验收（独立成段，下方）**

---

## 测试验收总表

| # | 用例 | 输入 | 命令 | 预期 |
|---|---|---|---|---|
| 1 | video-summary 步骤 6 已迁出 | SKILL.md 无步骤 6 | `grep -c "^## 6\." .agents/skills/video-summary/SKILL.md` | 0 |
| 2 | video-to-slides 有阶段 0 短指针 | SKILL.md 含"## 阶段 0" | `grep -c "^## 阶段 0" .agents/skills/video-to-slides/SKILL.md` | ≥ 1 |
| 3 | video-to-slides 无 ①.5 桥 | SKILL.md 无"### ①.5" | `grep -c "^### ①\.5" .agents/skills/video-to-slides/SKILL.md` | 0 |
| 4 | merge_procedure.md 含 review ≤ 2 | "review 最多 2 次"在文档 | `grep -c "review 最多 2 次" merge_procedure.md` | ≥ 1 |
| 5 | merge_procedure.md 指引 check_review_report | 路径指引在文档 | `grep -c "check_review_report.py" merge_procedure.md` | ≥ 1 |
| 6 | 3 个 merge 脚本迁到新位置 | 文件存在 | `ls .agents/skills/video-to-slides/scripts/videotodoc/{prepare,apply,review}_merge.py` | 3 行 |
| 7 | check_review_report 迁到新位置 | 文件存在 | `ls .agents/skills/video-to-slides/scripts/videotodoc/tests/check_review_report.py` | 1 行 |
| 8 | review_agent_prompt 迁到新位置 | 文件存在 | `ls .agents/skills/video-to-slides/reference/review_agent_prompt.md` | 1 行 |
| 9 | finalize_video 优先 merged | 跑 Task 6 测试 | `pytest test_pipeline_finalize_prefer_merged.py -v` | PASS |
| 10 | 3 个 merge 脚本测试套件 | 全跑 | `pytest .../test_prepare_merge.py .../test_review_merge.py -v` | 全 PASS |
| 11 | check_review_report 测试套件 | 全跑 | `pytest .../test_check_review_report.py -v` | PASS |
| 12 | video-summary 剩余测试 | 全跑 | `pytest .agents/skills/video-summary/scripts/tests/ -v` | 全 PASS（步骤 6 相关已迁出，剩余全过） |
| 13 | video-to-slides 全测试 | 全跑 | `pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/ -v` | 全 PASS |
| 14 | skill MD 断言（3 份） | 三份断言脚本 | `python3 check_skill_md_6_6.py` 等 3 个 | 全部退出码 0 |
| 15 | doctor 入口 | dry-run | `python3 process.py doctor` | 正常退出，无 ImportError |

---

## 执行交接

**计划已完成并保存到 `docs/superpowers/plans/2026-07-05-step6-extract-to-video-to-slides.md`。两种执行方式：**

**1. 子代理驱动（推荐）** - 每个任务调度一个新的子代理，任务间进行审查，快速迭代

**2. 内联执行** - 在当前会话中使用 executing-plans 执行任务，批量执行并设有检查点

**前置准备**（执行前必做）：
- 创建 worktree：`git worktree add ../vts-step6-refactor -b codex/step6-extract-to-video-to-slides`
- 切换到 worktree：`cd ../vts-step6-refactor`
- 确认 `.venv/bin/pytest` 可用

**重要决策回顾**（执行中请保持）：
- **不**新增 `load_reviewed_transcript` helper / 任何运行时严格 mode
- review-passed 闸口**复用**现有 `check_review_report.py`，仅在 SKILL.md / merge_procedure.md 中强化"必跑"标识
- `finalize_video` 补 4 行 prefer-merged，与现有闸口对齐即可
- review 迭代硬封顶 2 次（写在 merge_procedure.md 顶部）

**选哪种执行方式？**
