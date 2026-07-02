---

description: "Task list for 视频类型→转录分段策略"
---

# Tasks: 视频类型→转录分段策略

**Input**: Design documents from `/specs/001-video-type-segmentation/`（plan.md / spec.md / data-model.md / contracts/suggest-segments.md / quickstart.md）

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

**Tests**: 本特性全程 TDD——每个实现任务先写失败测试，跑红，再实现最小改动跑绿。Constitution II 非协商。

**Organization**: 按 4 个用户故事（功能区域）分组，每故事可独立实现与测试。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可并行（不同文件、无依赖）
- **[Story]**: US1–US4（见下）
- 含确切文件路径

## 用户故事

- **US1（P1 MVP）**：合并步骤能按视频结构形态套用不同分段策略（4 原型 + `suggest_segments(archetype)` 向后兼容）。
- **US2（P2）**：PPT/动画类视频用视觉事件（翻页）驱动分段，缺信号降级不崩。
- **US3（P2，与 US2 并行）**：类型判断归 Agent；脚本只给非决策统计提示（`signal_stats` 不输出 archetype）。
- **US4（P2）**：用户可指定/覆盖视频类型（三层证据 L1/L2/L3 + `--force-archetype`）。

---

## Phase 1: Setup

- [X] T001 确认基线：`.venv` + pytest 可用，`test_transcript_merge.py::TestSuggestSegments` 现有 4 例全绿
  ```bash
  PYTHONPATH=".agents/skills/video-to-slides/scripts:.agents/skills/_shared" \
    .venv/bin/python3 -m pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_transcript_merge.py::TestSuggestSegments -v
  ```

**Checkpoint**: 基线绿，可开始改动。

---

## Phase 2: Foundational（阻塞全部 US）⚠️ CRITICAL

- [X] T002 [US1] 新建 `.agents/skills/_shared/transcript_merge/strategies.py`：`SegmentStrategy` dataclass + `STRATEGY_REGISTRY`（4 原型纯数据）+ `get_strategy(archetype)`
- [X] T003 [US1] 新建测试 `.agents/skills/video-summary/scripts/tests/test_strategies.py`（先写，跑红）：
  - `test_registry_has_4_archetypes`（4 key 齐全）
  - `test_visual_event_requires_visual`（`visual_required=="required"`）
  - `test_get_unknown_raises`（KeyError）
- [X] T004 [US1] 实现 `strategies.py`，跑 T003 转绿

**Checkpoint**: 注册表就绪，US1 可开始。

---

## Phase 3: User Story 1 — 原型路由 + 向后兼容（P1 MVP）🎯

**Goal**: `suggest_segments(duration_ms, archetype="auto", visual_signals=None)` 已知原型用原型区间，`auto` 逐字节等价旧逻辑。
**Independent Test**: `suggest_segments(690000)` 旧签名返回 `target=34/chars=30-120`；`--archetype rescan_grid` 返回 `chars=60-220`。

### Tests for US1（先写先红）
- [X] T005 [US1] 在 `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_transcript_merge.py::TestSuggestSegments` 加：
  - `test_legacy_signature_unchanged`（690000→34、3600000→90、7200000→144 快照，Constitution III 非协商门）
  - `test_archetype_overrides_ranges`（rescan_grid → chars 60-220，target 仍 34，含 archetype 字段）

### Implementation for US1
- [X] T006 [US1] 在 `strategies.py` 实现 `resolve_suggestion(duration_ms, archetype, visual_signals)`（组合时长档 target/max + 原型策略 ranges/strategy）
- [X] T007 [US1] 改 `.agents/skills/_shared/transcript_merge/__init__.py` 的 `suggest_segments` 签名为 `(duration_ms, archetype="auto", visual_signals=None)`，`auto` 路径保留旧 if/elif 不变，已知路径委托 `resolve_suggestion`；返回新增 `archetype`/`strategy`
- [X] T008 [US1] 跑 T005 全绿（旧 4 + 新 2 = 6 例）

**Checkpoint**: US1 独立可用——原型路由生效且旧调用零回归。

---

## Phase 4: User Story 2 — 视觉信号 + ③降级（P2）

**Goal**: 原型③消费 `visual_signals.slide_boundaries_ms`；缺信号时 `warnings=["visual_missing"]` 不崩。
**Independent Test**: `suggest_segments(690000, archetype="visual_event", visual_signals=None)` 不抛异常、warnings 含 visual_missing。

### Tests for US2
- [X] T009 [US2] `test_strategies.py` 加 `test_visual_event_without_signals_warns` / `test_visual_event_with_signals`

### Implementation for US2
- [X] T010 [US2] `resolve_suggestion` 注入 `visual_signals`（仅③用）+ 缺失时 `warnings`；`__init__.py` 透传

**Checkpoint**: US2 独立可用——③可注入边界、可降级。

---

## Phase 5: User Story 3 — 非决策统计（P2，与 US2 并行 [P]）

**Goal**: `signal_stats.py` 纯统计，**不输出 archetype**（Constitution I 守护）。
**Independent Test**: `signal_stats("...")` 返回 dict 无 `"archetype"` 键，value 全 int。

### Tests for US3
- [X] T011 [P] [US3] 新建 `.agents/skills/video-summary/scripts/tests/test_signal_stats.py`：`test_no_archetype_in_output`、`test_counts_are_int`

### Implementation for US3
- [X] T012 [P] [US3] 新建 `.agents/skills/video-summary/signal_stats.py`：`signal_stats(transcript_text) -> dict[str,int]`，4 组信号词表 + 计数，无 archetype

**Checkpoint**: US3 独立可用——脚本不越界决策。

---

## Phase 6: User Story 4 — 用户指定/覆盖 + 三层证据（P2）

**Goal**: `prepare_merge.py` 接受 `--archetype`/`--force-archetype`/`--visual-signals`/`--tid`；`merge_input.json` 含 archetype+strategy；L3 回写刷新 ranges。
**Independent Test**: `prepare_merge ... --archetype topic_preserve` 输出 `chars=80-320`；改 `--archetype enumeration_unit` 重跑 → `chars=40-160`（ranges 随 archetype 刷新）。

### Tests for US4
- [X] T013 [US4] 集成测试：`--archetype rescan_grid` 输出含 archetype+strategy；L3 回写 ranges 刷新

### Implementation for US4
- [X] T014 [US4] 改 `.agents/skills/video-summary/scripts/prepare_merge.py`：加 4 参数 + 透传 + 自动探测同 run_dir `slides.json` 注入 slide_boundaries_ms + 可选打印 signal_stats 提示
- [X] T015 [US4] 缺 `--visual-signals` 且原型③时降级 warning 不崩

**Checkpoint**: US4 独立可用——用户可指定类型、CLI 端到端通。

---

## Phase 7: Documentation

- [X] T016 改 `.agents/skills/video-summary/SKILL.md`：合并步骤前加"原型判定"（4 原则 + 三层 L1/L2/L3 + 区域级混合 + `--force-archetype` 逃生舱）；③明确"有 slide_boundaries_ms 优先翻页点断、缺失降级①+②"
- [X] T017 `python3 -c "import markdown; markdown.markdown(open('...SKILL.md').read())"` 渲染校验

---

## Phase 8: Polish & Cross-Cutting

- [X] T018 端到端：资讯类真实 run `runs/内存暴涨.../transcript.json` 跑 `prepare_merge --archetype topic_preserve`
- [X] T019 端到端③：取一个 video-to-slides run 的 `slides.json` 作 `--visual-signals`，验证 slide_boundaries_ms 注入（若无可用 run 标注手动验证，逻辑已由 T009 单测覆盖）
- [X] T020 全量相关测试（见 quickstart §7）全绿

---

## Dependencies & Execution Order

### Phase 依赖
- **Phase 2 Foundational（T002-T004）** 阻塞全部 US。
- **US1（Phase 3）** 依赖 Phase 2；US2/US3 依赖 US1 的 `suggest_segments` 签名。
- **US2（Phase 4）与 US3（Phase 5）彼此 [P] 可并行**（不同文件：strategies/__init__ vs signal_stats）。
- **US4（Phase 6）** 依赖 US1+US2（透传 archetype + visual_signals）。
- **Docs（Phase 7）+ Polish（Phase 8）** 依赖全部 US。

### Within Each US
- 测试先写先红 → 实现 → 跑绿 → （用户确认后）每任务 commit。
- Constitution III：`suggest_segments(d)` 快照回归贯穿 US1。

### Parallel Opportunities
- T011/T012（US3 signal_stats）与 T009/T010（US2 visual_signals）[P] 并行。
- US3 全程不依赖 strategies.py，可独立先做。

---

## Notes

- [P] = 不同文件、无依赖。
- 测试先写并跑红再实现（Constitution II）。
- 不 commit 除非用户要求；commit 信息见 plan.md 各 Task 步骤5。
- ③ e2e（T019）依赖 video-to-slides 的 slides.json，现有 video-summary run 无此文件——优先单测覆盖，e2e 待有 video-to-slides run。

---

## Phase 9: Convergence

> 由 `/speckit-converge` 生成：对照 spec.md 验收标准 / 设计决策与 constitution 评估现状，补齐残留 partial 缺口。
> Constitution I–V 复检全通过，无 CRITICAL；以下 3 项均为 partial（功能已在，文档/测试覆盖待补）。

- [X] T021 在 `.agents/skills/video-summary/SKILL.md` 三层证据段补"L1/L3 冲突报告"裁定规则：agent 读全文做 L3 判定后，若与 L1 用户先验不同，**向用户报告分歧并说明按 L3 处理的理由**（AC#5 / 设计决策5，partial）。脚本侧 L1 先验/L3 回写/`--force-archetype` 已实现并测试，仅缺此 agent 指令。
- [X] T022 在 `test_strategies.py` 或 `test_transcript_merge.py` 加正向断言：`suggest_segments(d, archetype="visual_event")["strategy"]["anchors"]` 含 `"slide_change"`（AC#6，partial）。现有仅 rescan_grid 的负向断言。
- [X] T023 在 `test_review_merge.py` 加一例 archetype 专属区间（如 `chars_per_group_range="60-220"` rescan_grid）的客观检查，验证 `chars_above_max`/`chars_below_min`/`group_size_exceeded` 仍正确报告（AC#9，partial）。现有 18 例全用通用区间。
