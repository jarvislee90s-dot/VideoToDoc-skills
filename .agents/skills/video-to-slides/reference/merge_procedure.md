# 合并转录碎段流程（merge_procedure）

**用途**：video-to-slides 阶段 0 的合并流程权威描述。SKILL.md 阶段 0 只写短指针，全部细节、规则、示例都在本文件。

**前置产物**：`transcript.json`（来自 video-summary 的字幕或 ASR）
**产出**：`transcript_merged.json` + `merge_review_report.json`（含 `pass: true` + `self_review` 键）

---

## 接口约定

| 方向 | 文件 | 来源 / 去向 |
|------|------|-------------|
| 输入 | `transcript.json` | video-summary 阶段 1（字幕或 ASR 产出） |
| 输出 | `transcript_merged.json` | 进入 video-to-slides 阶段 1（process.py 使用） |
| 输出 | `merge_review_report.json` | 闸口校验 `check_review_report.py` 使用 |

> `transcript_merged.json` **只在 Review Agent 通过后才产出**，不通过则继续修正直到 pass。

---

## 1. 硬约束：review 最多 2 次

- 1st Review Agent 复核后如有 critical → 整理 agent 按意见修改 → 跑 `apply_merge` + `review_merge` + 2nd Review Agent
- 2nd Review Agent 仍发现 critical → **立即停止**，上报用户介入（"review 循环耗尽，2 次未通过"）
- 不允许无限制迭代
- 每次 Review Agent 跑完必须 `merge_review_report.json` 含 `self_review` 键（路径 A 或路径 B 标记）
- 阶段 0 收尾必跑：`python3 .agents/skills/video-to-slides/scripts/videotodoc/tests/check_review_report.py <run_dir>`，退出码必须 0（已有闸口，**沿用不重建**）

---

## 2. 合并转录碎段（必做，不可跳过）



**背景**：ASR 按语音停顿把句子切得太碎（平均 1-2 秒一句、半句话一段），
直接用于图文对齐会导致每页只有半句话。**必须**先合并再用于后续步骤。

**结构形态原型判定（prepare_merge 前必做）**：

合并前先判定视频的结构形态原型，再套对应分段策略。**类型判定归 agent，脚本不决策**
（`signal_stats` 只给计数提示）。4 个原型按"段落边界触发器"区分，两两策略不同：

| 原型 | 边界触发器 | 典型视频 | 策略要点 |
|---|---|---|---|
| `topic_preserve` | 话题/事件/时间转折 | 资讯、故事、访谈 | 线性切，宁少切勿多（粗） |
| `enumeration_unit` | 显式枚举标记（步骤词/序数词） | 教程、操作、盘点 | 一个枚举单元一段（细） |
| `visual_event` | 外部视觉事件（PPT 翻页/场景切换） | PPT 讲解、动画 | 硬边界优先，区间内再按语义子话题细分；**需视觉信号** |
| `rescan_grid` | 不能线性切、多对象多维度 | 多产品测评、对比 | 先扫全文建 item×维度 网格再分（重组） |

**三层证据（权威性递增，后者覆盖前者）**：
- **L1 用户先验**：用户声明类型 → `prepare_merge --archetype <原型>`（加权先验，agent 可 L3 覆盖）。
- **L2 标题+摘要**：纯规则预启视觉信号（标题/摘要含"PPT/课件/幻灯片"则预启翻页检测，非 LLM）；并作为 L3 上下文。
- **L3 全文权威**：agent 读全文判定原型。若与 L1 不同，**必须重跑** `prepare_merge --archetype <L3 原型>` 刷新 ranges——否则 review 阶段用旧区间误报。
- **L1/L3 冲突报告**：L3 高置信覆盖 L1（用户说的不一定对）；L3 与 L1 不同时，agent **向用户报告分歧**并说明按 L3 处理的理由，再按 L3 重跑。L3 低置信/模糊时，L1 用户先验作为裁定者打破平局。
- 用户确信、要跳过 L3 时：`--force-archetype <原型>`（绝对覆盖，跳过 L3）。
- 未给 `--archetype` 时脚本走 `auto`（回退时长档）并打印 `signal_stats` 计数提示，供 agent 做 L3 判定参考（计数非决策）。

**原型③（visual_event）视觉信号**：
- 翻页边界**复用** video-to-slides 的 `slides.json`：`prepare_merge --visual-signals <slides.json>`，或与 transcript 同 run_dir 时自动探测。
- 有 `slide_boundaries_ms` → 优先在翻页点断段，区间内再按语义子话题细分。
- 缺视觉信号 → 降级 `warnings=["visual_missing"]`，**不崩**；agent 改按 ①+②（话题/枚举）兜底分段。

**区域级混合**：一个视频可能跨原型（如前半教程②、后半测评④）。按区域套对应原型分段，不必全局统一。

**步骤**：
1. 运行 prepare_merge 生成合并输入清单（含目标段数建议 + 原型策略）：
   python3 .agents/skills/video-to-slides/.agents/skills/video-to-slides/scripts/videotodoc/prepare_merge.py \
     runs/<run_dir>/transcript.json \
     --archetype <topic_preserve|enumeration_unit|visual_event|rescan_grid>   # 可选，L1 先验；缺省 auto 回退时长档
2. 读取 runs/<run_dir>/merge_input.json（含 total_segments、suggestion、segments 清单）
3. 把相邻短句按语义合并为段落，写 runs/<run_dir>/merged_groups.json：
   [{"indices": [0,1,2,3,4,5,6,7,8], "text": "合并后的一段话"}, ...]
4. 运行 apply_merge 校验并落盘：
   python3 .agents/skills/video-to-slides/.agents/skills/video-to-slides/scripts/videotodoc/apply_merge.py \
     runs/<run_dir>/transcript.json runs/<run_dir>/merged_groups.json
   失败则按报错修正 merged_groups.json 出错的分组后重跑本步（断点重做，不全量重做）

**合并规则**（严格遵守）：
1. **原文保留**：完整保留每个短句的原文字，不删字、不改字、不加字、不调换顺序。
   你只在短句连接处插入标点。
2. **标点连接**：短句间加合适标点——逗号（停顿/并列/分句）、句号（句末）、
   分号（并列长句）、问号/感叹号（原句语气）、冒号（引出）。保留原问号感叹号。
3. **同话题聚合（最高优先级）**：描述同一件事/同一话题的相邻短句必须整到一段。
   话题转换处断段。宁可段数偏离目标，也要保证同话题完整。
4. **句法完整性（最高优先级）**：禁止把一个完整句子的依存成分拆到两段。
   以下情况必须并入同一段：
   - 程度/数量补语：如“价格暴涨/暴涨了”与“300%到500%”；
   - 数量宾语：如“达到/达到了”与“50亿美元”；
   - 时间/地点状语紧接说明：如“发生在”与“2024年”（由 review agent 按语义复核，客观脚本仅检查数字/百分比等明显补语）；
   - 列举项：同一组并列数据或例子不要拆散。
5. **段数软目标**：参考 `suggestion.target_segments` 和 `suggestion.per_group_range`。
   段数是软目标——同话题完整优先于凑段数。硬上限 `max_segments` 不可超。
6. **每段短句数约束**：尽量使每段包含的短句数落在 `suggestion.per_group_range` 范围内。
   若同话题较长，允许超出，但需在输出前自检并说明理由。
7. **每段字数区间**：每段合并后的中文字符数（含标点）建议落在 `suggestion.chars_per_group_range` 区间内。
   该区间是柔性参考，同话题完整优先；若必须超出，优先在同话题内部切分，而非强行压缩或跨话题拆断。
8. **索引完整**：indices 从 0 连续到末尾，覆盖全部短句，不重不漏；每段内连续递增。

**示例**：
输入：0.Harness这个词最近大火 1.但好像很少有人能说出它的准确定义
      2.但这又不妨碍很多人成天把它挂在嘴边 3.那这件事就比较奇怪了
      4.为什么一个连定义都还没有搞明白的抽象概念 5.会这么火热
      6.甚至代表了一个新的技术方向呢 7.别急
      8.今天这期视频就带你一口气了解Harness的来龙去脉
输出：{"indices": [0,1,2,3,4,5,6,7,8],
       "text": "Harness这个词最近大火，但好像很少有人能说出它的准确定义，但这又不妨碍很多人成天把它挂在嘴边。那这件事就比较奇怪了，为什么一个连定义都还没有搞明白的抽象概念，会这么火热，甚至代表了一个新的技术方向呢？别急，今天这期视频就带你一口气了解Harness的来龙去脉。"}

**注意**：apply_merge 只校验 index 结构（连续覆盖），不校验 text 内容，
所以你整理长句时个别字误差不会报错；只有 index 漏号/跳号/重复才报错，
且报错精确到具体分组，只需修正出错分组重写文件重跑。

### 2.1 Review Agent 复核合并质量（**必做，不可跳过**）

> ⚠️ **警告**：本步骤**必须**做一次 review，**不跑不许进入下一步**（摘要 / video-to-slides / feishu 发布）。执行方式按你的工具能力二选一。

**先判断能力**：检查你的可用工具是否有子代理调度能力（Claude Code 的 `Task`、Codex 的 `spawn_agent`、或配置 `multi_agent=true` 等）。

**路径 A（首选——支持子代理时）**：派一个独立子代理，把 `reference/review_agent_prompt.md` 作为其 system prompt 加载，让它复核 `merged_groups.json`。子代理与你上下文隔离，最严谨。

**路径 B（fallback——不支持子代理时）**：由你（当前 agent）加载 `reference/review_agent_prompt.md`，按其顶部的「路径 B · 上下文重置」四步自审（角色剥离 → 不凭记忆重读原始短句 → 强制挑刺 → 输出报告标注 `self_review: true`）。自审不如独立子代理彻底，必须更严格对照硬标准。

**步骤**：

1. 整理 agent 完成首次合并 → `merged_groups.json`
2. 跑 `apply_merge.py` 校验索引连续 → `transcript_merged.json`
3. 跑 `review_merge.py` 客观检查 → 初步 `merge_review_report.json`
4. **【必做】按路径 A 或 B 执行 review**，输出增强版 `merge_review_report.json`
5. 整理 agent 根据 critical issues **局部修正** `merged_groups.json`
6. 重跑 `apply_merge.py` + `review_merge.py` + review，直到 `pass=true`
6.5 **【必做】跑存在性校验**：`python3 .agents/skills/video-to-slides/scripts/videotodoc/tests/check_review_report.py <run_dir>`，退出码必须为 0。若报「缺少 self_review 键」，说明 review 未标注执行路径，回到步骤 4 重做。
7. **直到 pass 且校验退出码为 0 才进下一步**

**review agent 规则**：
- 只输出报告，不直接修改 `merged_groups.json`。
- critical 问题必须标记；warning 问题允许整理 agent 酌情处理。
- 所有判断必须基于 `merge_input.json` 中的约束数据，不能自行放宽。
- 遇到超出 `chars_per_group_range` 或 `per_group_range` 的段，先判断是否为“同话题完整”导致；若是，可接受为 warning；若不是，应建议切分。

**Prompt 模板 + 硬标准**：见 `reference/review_agent_prompt.md`（含句法完整性硬标准与判定信号）。

### 2.2 整理 agent 根据 Review Report 修正

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


---

## 3. 阶段 0 收尾闸口

```bash
python3 .agents/skills/video-to-slides/scripts/videotodoc/tests/check_review_report.py <run_dir>
```

- 退出码 0：进入阶段 1
- 退出码 1：缺 `self_review` 键，回到 2.1 重跑 Review Agent
- 退出码 2：报告文件不存在，说明没跑 `review_merge.py` 或 Review Agent

**不通过闸口禁止进入阶段 1。**

阶段 0 完成后必须存在：
- `transcript_merged.json`
- `merge_review_report.json`（含 `pass: true` + `self_review` 键，已被 `check_review_report.py` 校验）
