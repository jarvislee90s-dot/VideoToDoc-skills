# Implementation Plan: 视频类型→转录分段策略

**Branch**: `001-video-type-segmentation` | **Date**: 2026-07-02 | **Spec**: [design](../../../docs/superpowers/specs/2026-07-02-video-type-segmentation-strategy-design.md)

**Input**: Feature specification from `/specs/001-video-type-segmentation/spec.md`（软链到 `docs/superpowers/specs/2026-07-02-video-type-segmentation-strategy-design.md`）

> **面向 Agent 工作者**：必需子技能 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans，按任务逐项实现。步骤用复选框（`- [ ]`）跟踪，TDD 严格：失败测试→实现→跑绿→每任务 commit。

## Summary

把 video-summary 的转录合并按"结构形态原型"做可扩展分段策略：4 个原型（①话题保完整 / ②枚举按单元 / ③视觉事件 / ④全文重组）注册在 `STRATEGY_REGISTRY`，`suggest_segments` 扩展 `(duration_ms, archetype="auto", visual_signals=None)` 向后兼容。类型判断归 Agent（三层证据 L1用户/L2标题摘要/L3全文），脚本只供应策略与可选 `signal_stats` 提示，不决策。原型③的 PPT 翻页信号复用 video-to-slides 的 `detect_scene_changes`。

## Technical Context

**Language/Version**: Python 3.9+（本机 `.venv` 实际 3.14.4，代码须兼容 3.9 语法：`from __future__ import annotations`、`dict | None` 仅在注解或 ≥3.10——本仓库既有代码用 `from __future__ import annotations` 兼容，沿用之）

**Primary Dependencies**: 无新增第三方依赖。复用仓库既有：`pathspec`? 否；仅 stdlib（json/re/sys/pathlib/dataclasses）。`suggest_segments` 当前无依赖。

**Storage**: 文件系统（`merge_input.json` / `slides.json`），无数据库。

**Testing**: pytest 9.1.0（`.venv`）。回归基准：`test_transcript_merge.py::TestSuggestSegments` 现有 4 例（test_short_11min/1h/2h/tiny_video_floor）必须保持绿。

**Target Platform**: macOS（darwin），与既有 skill 一致。

**Project Type**: CLI 工具 + 共享库（`_shared/transcript_merge`），非 web。

**Performance Goals**: `suggest_segments` / `signal_stats` 纯计算，单次 < 50ms（转录 < 1M 字符）。无强约束，沿用既有量级。

**Constraints**: 
- 向后兼容（非协商）：`suggest_segments(duration_ms)` 旧签名逐字节等价。
- 脚本不决策（非协商）：`signal_stats.py` 不输出 archetype。
- 原型③缺 `visual_signals` 不崩溃，降级 warning。

**Scale/Scope**: 4 原型策略 + 1 classify/stats 模块 + 3 脚本签名扩展 + SKILL.md 增改。约 6-8 个任务。

## Constitution Check

*GATE: 必须在 Phase 0 前通过。Phase 1 设计后复检。*

| 原则 | 检查 | 通过 |
|---|---|---|
| I. 脚本只算约束不决策 | 类型判断归 Agent；`signal_stats` 只输出计数不输出 archetype；有测试守护 | ✅ 本计划 Task 5 明确"非决策"测试 |
| II. TDD | 每任务先写失败测试 | ✅ 全部任务遵循 |
| III. 向后兼容 | `suggest_segments(d)` 快照回归（690000→target34 等 4 例不变） | ✅ Task 2 含回归快照测试 |
| IV. 可扩展模块化 | 新增原型只加注册表一条 + 测试，不碰 prepare/apply/review 核心 | ✅ Task 1/4 设计如此 |
| V. 复用优先 | ③翻页用 `detect_scene_changes`/`detect_slides`，OCR 用 `extract_text` | ✅ Task 6 复用，不重写 |

**复检（Phase 1 后）**：确认 `resolve_suggestion` 不含"如何切"的命令式逻辑；`STRATEGY_REGISTRY` 条目为纯数据。✅ 预期通过。

## Project Structure

### Documentation (this feature)

```text
specs/001-video-type-segmentation/
├── plan.md              # 本文件
├── research.md          # Phase 0（技术选型确认）
├── data-model.md        # Phase 1（SegmentStrategy / suggestion / signal_stats 数据形状）
├── quickstart.md        # Phase 1（端到端验证手册）
├── contracts/           # Phase 1（suggest_segments / merge_input.json 接口契约）
│   └── suggest-segments.md
└── spec.md → 软链 docs/superpowers/specs/2026-07-02-...-design.md
```

### Source Code (repository root)

```text
.agents/skills/_shared/transcript_merge/
├── __init__.py          # 修改：suggest_segments 签名扩展，委托 strategies
└── strategies.py        # 新增：SegmentStrategy + STRATEGY_REGISTRY + resolve_suggestion

.agents/skills/video-summary/
├── signal_stats.py                         # 新增：纯统计提示，非决策
└── scripts/
    ├── prepare_merge.py                    # 修改：--archetype/--force-archetype/--visual-signals/--tid
    └── (review_merge.py / apply_merge.py)  # 不改逻辑，透传新字段

.agents/skills/video-summary/SKILL.md        # 修改：原型判定 + 三层证据 + 区域级混合

.agents/skills/video-to-slides/scripts/videotodoc/tests/
└── test_transcript_merge.py                 # 扩展：4 原型 + auto 回归 + signal_stats 非决策

.agents/skills/video-summary/scripts/tests/
├── test_signal_stats.py                     # 新增
└── test_strategies.py                      # 新增
```

**Structure Decision**: 沿用仓库既有布局——共享逻辑在 `_shared/transcript_merge`，skill 专属脚本在各自 `scripts/`，测试在对应 `tests/`。无新增顶层目录。

## Complexity Tracking

无 Constitution 违规需开脱。新增 `signal_stats.py` 一文件，但属 Constitution I 允许的"客观指标/提示"范畴（非决策），不需豁免。

---

## Phase 0: 研究（research.md 见同目录）

确认无外部未知：Python 3.9 兼容写法、`detect_scene_changes` 返回 `list[int]`(ms) 已核实、`Slide` dataclass 字段已核实。无 NEEDS CLARIFICATION。

## Phase 1: 设计产物

- `data-model.md`：`SegmentStrategy` dataclass、`suggestion` dict 形状、`signal_stats` 输出形状。
- `contracts/suggest-segments.md`：`suggest_segments` 签名契约 + `merge_input.json` 字段。
- `quickstart.md`：4 原型 + auto 回归 + ③注入边界 的端到端验证步骤。

---

## Tasks（TDD 逐任务）

### Task 1：`strategies.py` 骨架 + `STRATEGY_REGISTRY` 4 原型

**文件**：新增 `.agents/skills/_shared/transcript_merge/strategies.py`
**接口**：`SegmentStrategy` dataclass（principle/per_group_range/chars_per_group_range/paragraph_tendency/anchors/visual_required）；`STRATEGY_REGISTRY: dict[str, SegmentStrategy]` 4 条；`get_strategy(archetype) -> SegmentStrategy`。

- [ ] **步骤1：写失败测试** `test_strategies.py`
  ```python
  def test_registry_has_4_archetypes():
      from strategies import STRATEGY_REGISTRY, get_strategy
      assert set(STRATEGY_REGISTRY) == {"topic_preserve","enumeration_unit","visual_event","rescan_grid"}
  def test_visual_event_requires_visual():
      from strategies import get_strategy
      assert get_strategy("visual_event").visual_required == "required"
  def test_get_unknown_raises():
      import pytest
      from strategies import get_strategy
      with pytest.raises(KeyError): get_strategy("nope")
  ```
- [ ] **步骤2**：跑测试确认 FAIL（`ModuleNotFoundError: strategies`）。
  ```bash
  PYTHONPATH=".agents/skills/_shared" .venv/bin/python3 -m pytest .agents/skills/video-summary/scripts/tests/test_strategies.py -v
  ```
- [ ] **步骤3**：实现 `strategies.py`（4 条纯数据 + `get_strategy`）。
- [ ] **步骤4**：跑测试确认 PASS。
- [ ] **步骤5**：commit `feat(transcript_merge): 新增 strategies.py 4 原型注册表`。

### Task 2：`suggest_segments` 签名扩展 + `auto` 回归

**文件**：改 `.agents/skills/_shared/transcript_merge/__init__.py`
**接口**：`suggest_segments(duration_ms, archetype="auto", visual_signals=None)`；`auto`/未知 → 完全等同旧逻辑；已知 → 调 `resolve_suggestion`。

- [ ] **步骤1**：扩 `test_transcript_merge.py::TestSuggestSegments` 加回归快照（用已核实值）：
  ```python
  def test_legacy_signature_unchanged(self):
      # 旧签名逐字节等价（Constitution III 非协商回归门）
      assert suggest_segments(690_000) == {"target_segments":34,"per_group_range":"3-8","max_segments":120,"chars_per_group_range":"30-120"}
      assert suggest_segments(3_600_000)["target_segments"] == 90
      assert suggest_segments(7_200_000) == {"target_segments":144,"per_group_range":"12-25","max_segments":240,"chars_per_group_range":"120-400"}
  def test_archetype_overrides_ranges(self):
      s = suggest_segments(690_000, archetype="rescan_grid")
      assert s["chars_per_group_range"] == "60-220"  # 来自④而非时长档30-120
      assert s["target_segments"] == 34  # target 仍取自时长档
      assert s["archetype"] == "rescan_grid"
  ```
- [ ] **步骤2**：跑确认 `test_archetype_overrides_ranges` FAIL（KeyError/无 archetype 字段）。
  ```bash
  PYTHONPATH=".agents/skills/video-to-slides/scripts:.agents/skills/_shared" .venv/bin/python3 -m pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_transcript_merge.py::TestSuggestSegments -v
  ```
- [ ] **步骤3**：实现 `resolve_suggestion(duration_ms, archetype, visual_signals)` + 改 `suggest_segments` 委托之；`auto` 路径保留旧 if/elif 不变。
- [ ] **步骤4**：跑全部 `TestSuggestSegments` 确认 PASS（旧 4 例 + 新 2 例）。
- [ ] **步骤5**：commit `feat(transcript_merge): suggest_segments 支持 archetype，auto 向后兼容`。

### Task 3：`visual_signals` 通道 + ③降级不崩

**文件**：`strategies.py`（`resolve_suggestion` 注入 `visual_signals` 到 suggestion）、`__init__.py`（透传）。
**接口**：suggestion 新增 `visual_signals` 字段（仅原型③用 `slide_boundaries_ms`）；③缺信号时 `suggestion.warnings=["visual_missing"]` 不崩。

- [ ] **步骤1**：写测试 `test_visual_missing_does_not_crash`：
  ```python
  def test_visual_event_without_signals_warns():
      s = suggest_segments(690_000, archetype="visual_event", visual_signals=None)
      assert "visual_missing" in s.get("warnings", [])
      assert s["strategy"]["visual_required"] == "required"
  def test_visual_event_with_signals():
      s = suggest_segments(690_000, archetype="visual_event", visual_signals={"slide_boundaries_ms":[1000,5000]})
      assert s["visual_signals"]["slide_boundaries_ms"] == [1000,5000]
  ```
- [ ] **步骤2-4**：FAIL → 实现 → PASS。
- [ ] **步骤5**：commit `feat(transcript_merge): visual_signals 通道与③降级`。

### Task 4：`signal_stats.py` 纯统计 + 非决策守护

**文件**：新增 `.agents/skills/video-summary/signal_stats.py` + `test_signal_stats.py`
**接口**：`signal_stats(transcript_text) -> {原型: 命中计数}`，**不返回 archetype**。

- [ ] **步骤1**：写测试（Constitution I 守护）：
  ```python
  def test_no_archetype_in_output():
      from signal_stats import signal_stats
      out = signal_stats("首先点击保存，然后下一步。第三名是X。这款产品续航好。")
      assert "archetype" not in out  # 非决策：只给计数
      assert "enumeration_unit" in out and isinstance(out["enumeration_unit"], int)
  ```
- [ ] **步骤2-4**：FAIL → 实现（信号词表 + 计数，纯函数）→ PASS。
- [ ] **步骤5**：commit `feat(video-summary): signal_stats 非决策统计提示`。

### Task 5：`prepare_merge.py` 接受 `--archetype`/`--force-archetype`/`--visual-signals`/`--tid`

**文件**：改 `.agents/skills/video-summary/scripts/prepare_merge.py`
**接口**：透传 `archetype`/`visual_signals` 给 `suggest_segments`；`merge_input.json` 输出含 `archetype` + `strategy`；可选探测同 `run_dir` 的 `slides.json` 注入 `slide_boundaries_ms`；可选打印 `signal_stats` 提示。

- [ ] **步骤1**：集成测试——`prepare_merge.py --archetype rescan_grid` 输出含 `archetype:"rescan_grid"` 与 `strategy`。
- [ ] **步骤2**：FAIL。
- [ ] **步骤3**：实现参数 + 透传 + slides.json 自动探测。
- [ ] **步骤4**：PASS（含 L3 回写测试：首次 `--archetype enumeration_unit` ranges=②，改 `--archetype rescan_grid` 重跑 ranges=④）。
- [ ] **步骤5**：commit `feat(prepare_merge): 接受 archetype/visual-signals 参数`。

### Task 6：SKILL.md 增加原型判定 + 三层证据 + 区域级混合

**文件**：改 `.agents/skills/video-summary/SKILL.md`
**接口**：合并步骤前加"原型判定"（4 条原则 + 三层 L1/L2/L3 + 区域级混合 + `--force-archetype` 逃生舱）；③明确"有 slide_boundaries_ms 优先在翻页点断，缺失降级①+②"。

- [ ] **步骤1**：读当前 SKILL.md 合并段（已含⑤.6/⑤.7 review），定位插入点。
- [ ] **步骤2**：插入原型判定说明 + 类型相关合并提示。
- [ ] **步骤3**：`python3 -c "import markdown; markdown.markdown(open('...SKILL.md').read())"` 渲染校验。
- [ ] **步骤4**：commit `docs(video-summary): 增加结构形态原型判定与三层证据`。

### Task 7：端到端回归

- [ ] **步骤1**：对真实资讯 run `runs/内存暴涨.../transcript.json` 跑 `prepare_merge --archetype topic_preserve`，确认 ranges=①、输出含 strategy。
- [ ] **步骤2**：③e2e：注意现有 video-summary run 无 `slides.json`；需取一个 video-to-slides run 的 `slides.json` 作为 `--visual-signals`，验证 `slide_boundaries_ms` 注入。若无可用 run，标注为手动验证项 + 留单元测试覆盖（Task 3 已覆盖逻辑）。
- [ ] **步骤3**：全量相关测试。
  ```bash
  PYTHONPATH=".agents/skills/video-to-slides/scripts:.agents/skills/_shared:.agents/skills/video-summary/scripts" \
    .venv/bin/python3 -m pytest \
    .agents/skills/video-to-slides/scripts/videotodoc/tests/test_transcript_merge.py \
    .agents/skills/video-summary/scripts/tests/test_review_merge.py \
    .agents/skills/video-summary/scripts/tests/test_strategies.py \
    .agents/skills/video-summary/scripts/tests/test_signal_stats.py -v
  ```
- [ ] **步骤4**：commit `test: 视频类型分段策略端到端回归`（`--allow-empty` 如仅验证）。

## 自检

**规格覆盖度**：4 原型✓ / archetype 签名向后兼容✓ / visual_signals 通道✓ / ③降级✓ / signal_stats 非决策✓ / prepare_merge 参数✓ / SKILL 三层证据✓ / L3 回写✓ / review 透传✓ → 全覆盖。
**Placeholder 扫描**：无 TBD/TODO/“实现 later”。
**Constitution**：I-V 全通过，无豁免。
