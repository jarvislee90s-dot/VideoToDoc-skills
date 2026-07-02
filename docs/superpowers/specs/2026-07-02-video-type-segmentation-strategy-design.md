# 视频类型→转录分段策略设计

## 目标

让 video-summary 的转录碎段合并步骤，能**根据视频的结构形态选择不同的柔性分段策略**：
不同形态的视频，其"每段短句数 / 每段字数 / 目标段数 / 边界锚点"应有不同的柔性区间与切分倾向。

当前 `suggest_segments(duration_ms)` 仅按时长选档（≤15/≤30/≤60/>60min 四档），对所有视频一视同仁。
本设计在不破坏现有架构约束（**脚本只算约束与客观指标，分段决策权在 agent**）的前提下，把"结构形态
分类 + 对应分段策略"做成**可扩展模块**，使新增一种结构形态只需注册一条策略，不改核心流程。

## 背景：两类正交的分类

- **B站官方知识区分区（内容领域）**：科学科普 · 社科·法律·心理 · 人文历史 · 财经商业 · 校园学习 ·
  职业职场 · 设计·创意 · 野生技能协会（8 个二级分区，tid 124/228/207/208/209/229/122 等）。
  这是**内容领域**分类，与"如何分段"关系弱，仅作分类提示信号。
- **结构形态分类（分段真正关心的）**：按"段落边界由什么事件触发 + 切多细"分原型。
  这是**呈现/结构**维度，决定分段策略。

两者正交。本设计采用**结构形态原型**作为策略维度；`tid`/分区元数据仅作一个**免费的分类提示信号**。

## 设计原则（先于分类）

本设计遵循三条原则，分类法是它们的推论：

1. **按"边界触发器"分类，不按主题分类。** 决定分段策略的不是"这是数码测评还是家电测评"（主题），
   而是"段落边界由话题转折触发、还是枚举标记触发、还是视觉事件触发、还是需要跨全文重组触发"。
   主题相同但结构不同 → 策略不同；主题不同但结构相同 → 策略相同（如访谈与资讯都是①）。
2. **类型判断是语义决策，归 Agent；脚本只供应策略。** 与既定原则"脚本只算约束/客观指标，分段决策权在
   agent"一致。脚本不分类、不决策；它是一个**策略查询服务**，key 是 agent（或用户）声明的原型。
3. **一个视频可混合多个原型（按区域）。** "视频类型"只是主原型提示（供 target/ranges），真正的策略单位
   是**区域级原型**，由 agent 读转录时逐段判定。这能表达"教程=概述①+操作②"这类按主题分类做不到的混合。

## 结构形态原型（4 个，按边界触发器 × 算法区分）

每个原型由**一条原则**定义，例子只是说明不是定义。

| 原型 | 原则：边界由什么触发 × 算法 | 密度 | 视觉信号 | 典型形态（仅举例，非定义） |
|---|---|---|---|---|
| **① 话题驱动·保完整** `topic_preserve` | 边界=话题/事件/时间转折；**线性扫到即切**；宁少切勿多切，单段可长 | 粗 | 无 | 资讯/周报月报/故事叙事、深度解析/考据/视频论文、访谈对话（无说话人标注时按话题） |
| **② 枚举驱动·按单元** `enumeration_unit` | 边界=显式枚举标记（步骤词/序数词/item 词）；**一个枚举单元一段** | 细 | 无 | 教程操作段、盘点/排行榜、单产品逐项测评 |
| **③ 视觉事件驱动** `visual_event` | 边界=外部视觉事件（PPT 翻页/场景切换）；**硬边界优先**，事件区间内再按语义子话题细分 | 中 | **必需** | PPT/板书/白板/动画讲解、带幻灯片的讲座公开课 |
| **④ 全文重组** `rescan_grid` | 不能线性切；**先扫全文建结构（如 item×维度 网格）再分段** | 自适应 | 无（可辅助验证 item 数） | 多产品对比测评、横向横评 |

**原型两两策略不同**（粗保完整 / 细按单元 / 硬边界 / 重组算法），非凑数。

**区域级混合**（按主题分类做不到的能力）：
- 教程 = 概述段 ① + 操作段 ②
- 讲座/公开课 = ③（翻页）+ 段内 ①
- 多产品测评 = 引入 ① + 横评 ④ + 逐项 ②

> 访谈不再单列：无说话人分离时归 ①（话题/问答过渡即话题转折）。若有 diarization 标注，
> 说话人切换可作 ② 的枚举标记退化为 ②，但核心仍是"保完整"——故默认归 ①。
> 讲座/公开课不单列：= ③ ∪ ① 组合。

## 架构

```
transcript.json ──┐
                  ▼
   ┌──────────────────────────────────────────────────────┐
   │  整理 Agent（读转录，按原则逐区域判定原型）          │  ← 类型判断归 Agent（语义决策）
   │   主原型(供 target/ranges) + 区域级原型标签           │
   │   三层证据：L1 用户(--archetype 加权 / --force 绝对)  │
   │             L2 标题+摘要(早期提示/预启视觉信号)        │
   │             L3 全文(权威，高置信覆盖 L1)              │
   │   signal_stats 可选支撑 L3（非决策）                   │
   └──────────────────────────────────────────────────────┘
                  │ archetype
optional: video-to-slides 的 detect_scene_changes() / Slide[] ──┐  （仅原型③需要）
                  ▼                                              ▼
        ┌──────────────────────────┐   ┌─────────────────────────────┐
        │ transcript_merge.        │   │ STRATEGY_REGISTRY            │
        │  suggest_segments(       │◄──│  per archetype:              │
        │    duration_ms,          │   │   ranges + principle +       │
        │    archetype="auto",     │   │   anchors + visual_required  │
        │    visual_signals=None)  │   │  (4 条原型 + 可扩展)          │
        └──────────────────────────┘   └─────────────────────────────┘
                  │ suggestion = {target_segments, per_group_range,
                  │              chars_per_group_range, max_segments,
                  │              archetype, strategy:{principle, anchors,
                  │              paragraph_tendency, visual_required}}
                  ▼
        merge_input.json ──► 整理 agent（按 strategy 分组，区域级用对应原型）──► review agent ──► review_merge.py（客观检查）
```

**关键原则不变**：脚本只产出**柔性区间 + 原则提示 + 客观检查指标**；分段决策始终由整理 agent 和 review
agent 做语义判断。原型策略只是让 agent 拿到更贴合该结构的约束与提示。

## 关键设计决策

### 1. 扩展 `suggest_segments` 签名，保持向后兼容

```python
def suggest_segments(
    duration_ms: int,
    archetype: str = "auto",          # topic_preserve|enumeration_unit|visual_event|rescan_grid|"auto"
    visual_signals: dict | None = None,  # {"slide_boundaries_ms":[...], ...} 原型③必需，其余忽略
) -> dict
```

- `archetype="auto"`（或缺省/未知）时，**完全回退到现有时长四档逻辑**：返回字节等价旧 4 键 dict（无 `archetype`/`strategy` 键，Constitution III 逐字节等价）。
- 已知原型时，以该原型策略的区间为基准，再按时长四档做 target/max_segments 夹取（见决策 3），返回字典**新增** `archetype` 与 `strategy` 字段，供 `merge_input.json` 透传给 agent。

### 2. 策略注册表 `STRATEGY_REGISTRY`（可扩展核心，按原型 key）

每条策略是一个纯数据条目（原则 + 区间 + 倾向 + 锚点 + 视觉需求），无行为分支，新增原型只加一条：

```python
# .agents/skills/_shared/transcript_merge/strategies.py
STRATEGY_REGISTRY: dict[str, SegmentStrategy] = {
    "topic_preserve": SegmentStrategy(        # ① 话题驱动·保完整
        principle="边界=话题/事件/时间转折；线性扫到即切；宁少切勿多切",
        per_group_range="6-15",
        chars_per_group_range="80-320",
        paragraph_tendency="preserve_natural_paragraphs_coarse",
        anchors=["topic_transition_words", "time_markers", "qa_transition"],
        visual_required="none",
    ),
    "enumeration_unit": SegmentStrategy(      # ② 枚举驱动·按单元
        principle="边界=显式枚举标记；一个枚举单元一段",
        per_group_range="3-8",
        chars_per_group_range="40-160",
        paragraph_tendency="one_marker_unit_per_segment",
        anchors=["step_words", "ordinal_words", "item_markers"],
        visual_required="none",
    ),
    "visual_event": SegmentStrategy(          # ③ 视觉事件驱动
        principle="边界=外部视觉事件(PPT翻页/场景切换)；硬边界优先，区间内再细分",
        per_group_range="4-12",
        chars_per_group_range="50-240",
        paragraph_tendency="visual_boundary_then_subtopic",
        anchors=["slide_change", "scene_change", "heading_text"],
        visual_required="required",           # 必须有 slide_boundaries_ms
    ),
    "rescan_grid": SegmentStrategy(           # ④ 全文重组
        principle="不能线性切；先扫全文建 item×维度 网格再分",
        per_group_range="5-12",
        chars_per_group_range="60-220",
        paragraph_tendency="scan_then_grid_item_dimension",
        anchors=["item_markers", "dimension_words", "comparison_markers"],
        visual_required="none",
    ),
}
```

> **原型 key 用英文稳定 ID**，便于代码与配置引用。策略条目只含**原则 + 区间 + 倾向 + 锚点 + 视觉需求**，
> 不含任何"如何切"的命令式逻辑——切分仍由 agent 决定。

### 3. 区间与时长解耦：原型给区间形状，时长给缩放

避免"原型区间"和"时长区间"互相打架：

- 原型策略给出**基准区间**（per_group / chars / 倾向 / 锚点 / 原则）。
- 时长档（≤15/≤30/≤60/>60min）给出 `target_segments` 公式与 `max_segments` 上限，沿用现有逻辑。
- 最终 `suggestion`：`target_segments`、`max_segments` 取自时长档；`per_group_range`、`chars_per_group_range`、
  `strategy` 取自原型策略；两者并列呈现，agent 综合裁量（同话题完整始终最高优先）。

### 4. `visual_signals` 通道复用 video-to-slides 已有能力（不重新造轮子）

- **原型③的 PPT 翻页**：直接复用 `video-to-slides/videotodoc/slides.py::detect_scene_changes()`
  返回的场景切换点（`list[int]` ms）作为 `slide_boundaries_ms`；OCR 大字标题复用
  `ocr.py::extract_text()` 的 Slide.ocr_text。
- 传参方式：`prepare_merge.py` 增加可选 `--archetype` 与 `--visual-signals <path/to slides.json>`；
  若 video-to-slides 已在同一 run_dir 跑过，自动探测 `slides.json` 并注入 `slide_boundaries_ms`。
- 原型③在缺少 `visual_signals` 时**不崩溃**：降级为"文本主导 + 标注视觉缺失 warning"，agent 仍可按
  标题/语义子话题切分（退化为 ①+② 的混合）。

### 5. 三层渐进式原型判定（evidence hierarchy）；决策权在 Agent

类型判断是语义决策，归 Agent；脚本不分类、不决策（脚本只**收集证据**）。判定按证据可得时点分三层，
**全文层（L3）权威**：

| 层 | 时机 | 输入 | 角色 |
|---|---|---|---|
| **L1 用户** | 技能触发时（`--archetype` 或 agent 问用户，可跳过） | 用户口述/选择 | 强先验，**非绝对**（用户可能误判，如把"多产品横评"说成"测评"而实为④） |
| **L2 标题+摘要** | 取平台元数据时（视频 title/description，非生成的摘要） | 平台 title/desc | 早期提示：①轻量关键词预启可能需要的视觉信号（标题含"PPT/课件/教程"则预启翻页检测，非 LLM）；②作为 L3 agent 的上下文 |
| **L3 全文** | 合并时（整理 agent 读完整转录） | 完整 transcript | **权威判定**：结构形态从全文最清晰 |

**裁定规则**：
- L3 高置信 → L3 胜，即使与 L1 冲突（用户说的不一定对）。
- L3 低置信/模糊（如①与④难分）→ L1 用户先验作为**裁定者**打破平局（这就是"取一定权重"的落点）。
- L2 始终为提示/上下文，不单独裁定。
- L1 与 L3 冲突时，agent **向用户报告分歧**并说明按 L3 处理的理由。
- **逃生舱**：`--force-archetype <id>`（区别于 `--archetype`）为用户**绝对**覆盖，跳过 L3，用于用户确信正确、疑 L3 误判时。

**两层原型概念澄清**：
- 3 层产出的是**视频级主原型**（供 `target/ranges` + 策略提示）。
- **区域级原型**（一视频混合①+②等）仍由整理 agent 在合并时按 4 条原则逐区域判定，3 层系统不管区域级。

**`signal_stats.py`（可选，支撑 L3）**：纯统计工具，打印各原型信号词命中计数供 L3 agent 参考，**非约束、非决策**，可忽略，失败不影响流程。

这与既定原则一致：类型判断是语义决策 → 归 agent；脚本不分类、不决策。

### 6. `merge_input.json` 扩展字段（向后兼容，仅新增）

```json
{
  "total_segments": 690,
  "duration_ms": 1320000,
  "suggestion": {
    "target_segments": 90,
    "per_group_range": "5-12",
    "chars_per_group_range": "60-220",
    "max_segments": 120,
    "archetype": "rescan_grid",
    "strategy": {
      "principle": "不能线性切；先扫全文建 item×维度 网格再分",
      "paragraph_tendency": "scan_then_grid_item_dimension",
      "anchors": ["item_markers", "dimension_words", "comparison_markers"],
      "visual_required": "none"
    }
  },
  "segments": [...]
}
```

整理 agent 与 review agent 读 `suggestion.strategy` 据此调整分组倾向；区域级混合时，agent 对不同区域套用
对应原型的原则。`review_merge.py` 的客观检查项（短句数/字数区间/句法断裂）仍按 `suggestion` 区间执行，
逻辑不变。

## 组件

### `transcript_merge/strategies.py`（新增）
- `SegmentStrategy` dataclass、`STRATEGY_REGISTRY`（4 条原型）、`get_strategy(archetype) -> SegmentStrategy`。
- `resolve_suggestion(duration_ms, archetype, visual_signals) -> dict`：组合时长档 + 原型策略，产出最终 `suggestion`。

### `transcript_merge/__init__.py`（修改）
- `suggest_segments` 签名扩展为 `(duration_ms, archetype="auto", visual_signals=None)`，
  内部委托 `strategies.resolve_suggestion`；`auto` 路径完全等同旧行为。

### `video_summary/signal_stats.py`（新增，可选，非决策）
- `signal_stats(transcript_text) -> {原型: 命中计数}` 纯统计；`prepare_merge` 可选打印供 agent 参考。
- 无决策、无阈值、不输出 archetype；仅提示。

### `video-summary/scripts/prepare_merge.py`（修改）
- 增加 `--archetype`、`--visual-signals`、`--tid`（提示用）参数。
- 调 `suggest_segments(duration_ms, archetype, visual_signals)`；若未指定 archetype 则 `auto`（回退时长档），
  并可选打印 `signal_stats` 提示供 agent 自行判断。
- `merge_input.json` 的 `suggestion` 字段：**已知原型**时含 `archetype` + `strategy`（+ 原型③的 `visual_signals`/`warnings`）；
  **`archetype="auto"`（缺省/未知）时为字节等价旧 4 键 dict，不含 `archetype`/`strategy`/`visual_signals`/`warnings` 键**（Constitution III 非协商回归门，见 data-model.md / contracts/suggest-segments.md）。
- **L3 回写流程**：prepare_merge 首次输出用 L1（或 auto）的 archetype 与 ranges；整理 agent 读全文做 L3 判定后，若 archetype 变化，**重跑** `prepare_merge.py --archetype <L3>` 刷新 `merge_input.json` 的 ranges/strategy，再执行合并——保证 review 阶段的客观检查区间与最终 archetype 一致（避免"agent 改了型但 ranges 还是旧的"导致 review 误报）。

### `video-summary/SKILL.md`（修改）
- 技能触发时（步骤1前后）**可选询问用户**视频类型，或接受 `--archetype`（加权先验）/`--force-archetype`（绝对覆盖）参数；用户可跳过（跳过则靠 L2/L3）。
- 合并步骤前增加"**原型判定**"说明：4 条**原则**（边界触发器）+ 区域级混合 + 主原型概念；agent 按原则语义判定，不靠死词表。
- **三层渐进判定**写进 SKILL.md：L1 用户先验(加权) → L2 标题+摘要早期提示(含预启视觉信号) → L3 全文权威；L3 高置信覆盖 L1，L3 模糊时 L1 裁定；L1/L3 冲突时报告用户。
- 合并规则中按 `strategy.principle` 与 `strategy.anchors` 给出**原型相关**的分组提示（仍是软约束，
  同话题完整最高优先）。
- 原型③明确："若 `visual_signals.slide_boundaries_ms` 存在，优先在翻页点断段；缺失则降级为①+②混合并 warning"。

### `review_merge.py`（不改逻辑，仅透传）
- 客观检查仍按 `suggestion` 区间执行；新增字段对它透明。

## 验收标准

1. 新增 4 条原型策略，每条含 principle/per_group_range/chars_per_group_range/paragraph_tendency/anchors/
   visual_required 齐全，`STRATEGY_REGISTRY` 可被 `get_strategy` 检索。
2. `suggest_segments(duration_ms)`（旧签名，无 archetype 参数）行为与改动前**逐字节一致**，既有测试全绿。
3. `suggest_segments(duration_ms, archetype="rescan_grid")` 返回的 `chars_per_group_range` 取自该原型策略而非时长档。
4. 类型判断**不在脚本中发生**：`signal_stats.py` 只输出命中计数，不输出 archetype、不做决策；3 层判定（L1 用户 / L2 标题摘要 / L3 全文）均由 agent 或用户做语义判断。
5. 三层裁定：L3 全文高置信时覆盖 L1 用户先验（测试：`--archetype enumeration_unit` 但全文为横评 → 最终 `archetype=rescan_grid` 且报告冲突）；L3 低置信时 L1 裁定；`--force-archetype` 绝对覆盖跳过 L3。
6. `prepare_merge.py --archetype visual_event --visual-signals slides.json` 时，`merge_input.json` 的
   `suggestion.strategy` 含 `anchors:["slide_change"]` 且 `slide_boundaries_ms` 注入成功。
7. 原型③在缺少 `visual_signals` 时**不崩溃**，降级为"文本主导 + 视觉缺失 warning"，agent 仍可工作。
8. 新增原型只需在 `STRATEGY_REGISTRY` 注册一条 + 在 SKILL.md 加一组原则要点，**无需改动** `prepare_merge`/
   `apply_merge`/`review_merge` 核心逻辑。
9. `review_merge.py` 对新区间仍正确报告 `chars_above_max`/`chars_below_min`/`group_size_exceeded`。
10. 至少新增 6 个测试：4 原型策略解析 + 1 个"auto 回退与旧逻辑一致"回归 + 1 个"signal_stats 非决策"。

## 测试策略

1. **单元测试**
   - `strategies.get_strategy("visual_event")` 返回字段齐全且 `visual_required=="required"`。
   - `resolve_suggestion` 组合时长档 `target_segments` + 原型策略区间，字段互不覆盖。
   - `signal_stats` 对含步骤词的文本返回高计数，但**不返回 archetype**（验证非决策）。
   - 旧签名 `suggest_segments(d)` 与改动前快照一致（回归）。
2. **集成测试**
   - `prepare_merge.py --archetype rescan_grid` 输出 `merge_input.json` 含 `archetype:"rescan_grid"` 与 `strategy`。
   - `--visual-signals` 注入 `slide_boundaries_ms` 成功；缺文件时 warning 不崩。
   - **L3 回写**：首次 `--archetype enumeration_unit` 输出 ranges=②区间；改 `--archetype rescan_grid` 重跑后 ranges 变为④区间，验证 ranges 随 archetype 一致刷新。
3. **回归测试**
   - 既有 `test_transcript_merge.py::TestSuggestSegments` 4 例全绿（无 archetype 参数路径不变）。
   - 既有 `test_review_merge.py` 5 例全绿。
4. **端到端**（用现有 run 目录）
   - 对一个真实 PPT 类转录，`--archetype visual_event` + 注入幻灯片边界，整理 agent 在翻页点断段比例显著高于无策略时。
   - 对一个资讯/故事类转录，`--archetype topic_preserve`，整理 agent 段数明显少于 enumeration_unit 时，且段落更完整。

## 不做什么

- 不在脚本里做类型判断/分段决策：原型只给区间与原则提示，"判什么型、在哪里断"始终由 agent 判断。
- 不重新实现 PPT 翻页检测/OCR：复用 video-to-slides 的 `detect_scene_changes`/`extract_text`。
- 不调大模型做分类：类型判断由 agent 在合并时按原则语义完成；`signal_stats` 是纯词频统计，不联网不调模型。
- 不把"内容领域"（科学科普/人文历史…）作为策略维度——那是正交维度，仅作分类提示信号。
- 不做"固定例子→原型"映射表：原型由原则定义，例子仅作说明，避免新例子落到映射外导致错分。
- 不破坏向后兼容：`suggest_segments(duration_ms)` 旧行为与既有测试必须不变。
- 不在本期实现说话人机位检测：访谈默认归 ①，有 diarization 时 agent 可按说话人切换作枚举标记退化为 ②。
- 不强行把所有视频塞进 4 原型之一——主原型低置信时回退 `auto`，按通用时长档分段；区域级混合是常态。

## 扩展示例（未来如何加一种结构形态）

新增"直播切片/精华"形态只需：
1. `strategies.py` 加一条 `"live_highlight": SegmentStrategy(principle=..., ...)`。
2. `signal_stats.py` 信号词表加一组（"刚才/高能/这里/弹幕"等，仅提示用）。
3. SKILL.md 原则要点补一条。
4. 加一个单测。无需触碰 `prepare_merge`/`apply_merge`/`review_merge`。
