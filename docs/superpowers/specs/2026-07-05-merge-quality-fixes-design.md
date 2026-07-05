# 合并质量修复设计

**日期**：2026-07-05
**作者**：Codex 协作完成
**状态**：待用户审查

## 1. 背景

视频整理流程 `video-summary` + `video-to-slides` 跑下来发现两个 bug：

- **Bug 1**：`restore_images.py` 默认 `sync_toc` 会把紧凑版"## 图文讲义"和首个 `### 第 N 页` 之间的所有内容当 TOC 抓取，覆盖 agent 写在整理版的目录。同时由于 sync_toc 误把"第 1 页全部内容"插入为子目录，整理版最终文件里第 1 页出现两次（占位版+整理版）。
- **Bug 2**：整理 agent 跳过了 SKILL 文档 6.6 节要求的"独立 review agent"步骤。`review_merge.py` 客观脚本只检测"数字/程度补语"被切（如"暴涨 300%"），不检测"主谓/状语"被切（如"让每个词"+"都包含 X"），导致图文讲义出现断句。

## 2. 根因

### 2.1 Bug 1 根因：sync_toc 误抓

- `extract_toc_from_compact`（`restore_images.py:22-37`）用 `r'## 图文讲义\n\n(.*?)\n\n### 第 \d+ 页'` + `re.DOTALL`，让 `.*?` 跨行匹配
- 当紧凑版没有真目录时（`## 图文讲义` 后紧跟 `### 第 1 页`），toc 抓取到第 1 页全部内容（~230 字符）
- toc 非空触发 `sync_toc` 替换分支，把整理版 H1 后到第一个 `### 第 N 页` 之间的内容（即 agent 写的"## 目录"+"## 第一章"）覆盖成"### 第 1 页 + 图片 + 原始 ASR"
- 整理版"### 第 1 页 · 开场立意"作为 subn 后的首个 `### 第 N 页` 保留 → **第 1 页在最终文件里出现两次**

**根因**：脚本在替 agent 决策（同步目录），但 agent 自己会写目录；脚本"好心"反而破坏了 agent 的输出。

### 2.2 Bug 2 根因：跳过 review agent 步骤

两层问题：

- **流程层**：SKILL 文档 6.6 节**没说"必做"**，只描述了流程——agent 容易跳过
- **工具层**：`review_merge.py` 已有 `_has_syntax_break` 启发式（line 49-58），但只检测"数字/程度补语"被切（`_SYNTAX_HINT_ENDINGS = 上涨/下降/增长/...` + `_NUMBER_LIKE_RE`）；**不检测**"主谓/状语"被切
- 客观脚本与 LLM 复核的分工是清晰的：
  - 客观脚本能 100% 准确检测"数字补语"被切（确定性规则）
  - "主谓/状语"被切需要 LLM 理解语义才能识别，客观脚本做不到
- commit `2e8e564d fix(video-summary): 降低 review_merge 句法断裂启发式误报率` 之前有过误报，已经把"是/了/到/为"等高频虚词从启发式中移除——说明这条启发式已经调到合理水位，**不要再加新启发式**

## 3. 设计目标

1. **Bug 1**：删除 `restore_images.py` 的目录同步功能（`sync_toc` + `extract_toc_from_compact`），让脚本只做"图片恢复"这一件事；目录由 agent 写。
2. **Bug 2**：在 `SKILL.md` 6.6 节强化 review agent 流程，明确"必做，不可跳过"，内联完整提示词模板。
3. **不动**：`review_merge.py`、`process.py`、`cli.py` 等其他脚本。

## 4. 改动清单

### 4.1 `restore_images.py`：删除 sync_toc

删除内容（按当前文件 line 号）：
- `extract_toc_from_compact` 函数（line 22-37）
- `sync_toc` 函数（line 40-77）
- `restore_images` 函数中的 `if sync_toc_enabled: sync_toc(...)` 调用（line 130-131）
- `restore_images` 函数的 `sync_toc_enabled` 参数（line 119）
- `main` 中的 `--no-sync-toc` 解析（line 148-149）
- `sync_toc_enabled = "--no-sync-toc" not in args`（line 153）
- 模块 docstring 中"默认同时把紧凑版中 ## 图文讲义 与第一个 ### 第 N 页 之间的目录同步到整理版"这句话
- `main` 的 usage 中 `--no-sync-toc` 参数

保留内容：
- `extract_images_from_compact` 函数（line 80-92）
- `restore_images` 函数去掉 `sync_toc_enabled` 参数后的图片恢复逻辑
- `main` 的命令行解析（去掉 `--no-sync-toc`）

### 4.2 `video-summary/SKILL.md` 6.6 节：重写

新 6.6 节内容包含：
- **强制流程**说明（最严厉语气）
- **为什么强制**说明（区分客观脚本和 LLM 复核的分工）
- **完整步骤**（5 步）
- **review agent 提示词模板**（内联完整内容）
- **review agent 规则**（只输出报告、不直接修改等）

## 5. 具体内容

### 5.1 `restore_images.py` 改动后的 main()

```python
def main() -> int:
    args = sys.argv[1:]
    if len(args) < 2:
        print("用法：python3 restore_images.py <compact_md> <semantic_md>", file=sys.stderr)
        return 1

    compact_path = Path(args[0]).expanduser().resolve()
    semantic_path = Path(args[1]).expanduser().resolve()

    try:
        restore_images(compact_path, semantic_path)
        return 0
    except FileNotFoundError as e:
        print(f"❌ 错误：{e}", file=sys.stderr)
        return 2
```

### 5.2 `restore_images()` 改动后的签名

```python
def restore_images(compact_path: Path, semantic_path: Path) -> Path:
    """用紧凑版的图片路径替换整理版中的占位符。"""
    if not semantic_path.exists():
        raise FileNotFoundError(f"整理版不存在：{semantic_path}")
    if not compact_path.exists():
        raise FileNotFoundError(f"紧凑版不存在：{compact_path}")

    images = extract_images_from_compact(compact_path)
    # ... 后续图片替换逻辑不变
```

### 5.3 `SKILL.md` 6.6 节新内容

```markdown
### 6.6 Review Agent 复核合并质量（**必做，不可跳过**）

> ⚠️ **警告**：本步骤**必须**独立 subagent 跑一次，**不跑不许进入下一步**（摘要 / video-to-slides / feishu 发布）。

**为什么强制**：
- `review_merge.py` 客观脚本**只检测数字/程度补语**被切（如"暴涨 300%"），**不检测"主谓/状语"被切**（如"让每个词"+"都包含 X"）
- 后者需要 LLM 理解语义才能识别，客观脚本做不到
- 跳过这一步会导致图文讲义断句（每张图之间出现半句话）
- 客观脚本报的 0 critical **不能**代替 review agent 复核

**步骤**：

1. 整理 agent 完成首次合并 → `merged_groups.json`
2. 跑 `apply_merge.py` 校验索引连续 → `transcript_merged.json`
3. 跑 `review_merge.py` 客观检查 → 初步 `merge_review_report.json`
4. **【必做】派独立 subagent 复核**（按下面的"review agent 提示词模板"）：
   - subagent 读 `merge_input.json` + `merged_groups.json` + `merge_review_report.json`
   - 按 5 项清单复核（句法完整性、同话题聚合、字数、段大小、索引）
   - 输出**增强版** `merge_review_report.json`（覆盖原文件）
5. 整理 agent 根据 critical issues **局部修正** `merged_groups.json`
6. 重跑 `apply_merge.py` + `review_merge.py` + subagent 复核，直到 `pass=true` 或只剩可接受 warning
7. **直到 pass 才进下一步**

#### review agent 提示词模板（**必用，不可改写核心规则**）

```
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
```json
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
```

## 硬规则
- **只输出报告，不直接修改 merged_groups.json**
- 严重性只有 `critical` / `warning` 两级
- `pass` 在所有 issues 都是可接受 warning 时为 true，有 critical 时为 false
- 不要放宽或跳过清单任何一项
```

**review agent 规则**（保留原内容）：
- 只输出报告，不直接修改 `merged_groups.json`。
- critical 问题必须标记；warning 问题允许整理 agent 酌情处理。
- 所有判断必须基于 `merge_input.json` 中的约束数据，不能自行放宽。
- 遇到超出 `chars_per_group_range` 或 `per_group_range` 的段，先判断是否为"同话题完整"导致；若是，可接受为 warning；若不是，应建议切分。
```

## 6. 测试用例

### 6.1 Bug 1 回归测试

- **输入**：agent 写好的整理版（含 `## 目录` + 章节列表 + `## 第一章`）
- **跑**：`python3 restore_images.py <compact_md> <semantic_md>`
- **期望**：
  - 整理版 H1 后到第一个 `### 第 N 页` 之间的内容**完全保持不变**
  - 每张图的占位符 `<!-- IMAGE:N -->` 被替换为实际图片路径
- **验证方法**：diff 跑前跑后的整理版，差异只在图片行

### 6.2 Bug 2 流程验证

- **流程**：
  1. 整理 agent 合并 → `merged_groups.json`
  2. 跑 `review_merge.py` → 客观 `merge_review_report.json`（含/不含 critical）
  3. 派 subagent 复核 → 增强版 `merge_review_report.json`
  4. 整理 agent 根据 critical 局部修正 `merged_groups.json`
  5. 重跑 `apply_merge.py` + `review_merge.py` + subagent 直到 `pass=true`
  6. 才进下一步
- **期望**：整理版图文讲义**没有跨页断句**（如"让每个词"和"都包含 X" 在同一页）

## 7. 风险与回滚

- **风险**：
  - 删除 `sync_toc` 后，原本"自动同步紧凑版目录到整理版"的功能消失——但这正是修复目标
  - SKILL.md 6.6 节加入 review agent 强制流程后，agent 不能跳过——这是修复目标
- **回滚**：
  - 改动范围小（1 个 Python 文件 + 1 个 SKILL 文档）
  - `git revert` 即可回滚
- **向后兼容**：
  - 删掉 `--no-sync-toc` 标志后，旧命令行（带 `--no-sync-toc`）会被忽略（argparse 行为），不影响功能
  - 实际现有用户没有依赖 `sync_toc`（前面跑 A 目录时也没传过 `--no-sync-toc`）

## 8. 不做（YAGNI）

- **不动 `review_merge.py`**：用户明确说不要通过脚本拦截，且现有启发式已调到合理水位
- **不动 `process.py` / `cli.py`**：本次修复不需要
- **不**为 `sync_toc` 加新功能（如"自动跳过已写目录"）——直接删，符合 YAGNI
- **不**改 review agent 提示词的核心规则——保持简洁，不增加维护成本
- **不**做"agent 写目录"专用工具——agent 自己有写 markdown 能力，工具不该替 agent 决策

## 9. 验收标准

- 修复后跑一次 `video-summary` + `video-to-slides` 流程：
  - agent 写好目录的整理版**不被覆盖**（验证 Bug 1 修复）
  - 整理 agent **强制跑 review agent subagent**（验证 Bug 2 流程）
  - 整理版图文讲义**没有跨页断句**（验证 Bug 2 效果）

## 10. 改动汇总

| 文件 | 改动量 | 风险 |
|---|---|---|
| `.agents/skills/video-to-slides/scripts/restore_images.py` | 删除 ~60 行 | 低（删除而非修改） |
| `.agents/skills/video-summary/SKILL.md` | 6.6 节重写 +90 行 | 低（文档级） |

总共：1 个 Python 文件删除 ~60 行，1 个 SKILL 文档加 ~90 行。

