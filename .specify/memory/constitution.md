# VideoToDoc-skills Constitution

## Core Principles

### I. 脚本只算约束，不决策（非协商）

脚本只计算客观指标与柔性约束（目标段数、短句区间、字数区间、index 结构校验）。
语义判断与分段决策权始终在整理 agent 和 review agent。类型判断属语义决策，归 agent，不归脚本。
新增"分类/决策"型脚本前必须回答：这个判断能不能移到 agent？能就不在脚本里做。

### II. 测试先行（TDD，非协商）

每个行为改动先写失败测试，再实现最小改动，跑绿后提交。Red-Green-Refactor 严格执行。
回归测试：改动向后兼容路径必须有"旧签名/旧行为快照一致"的回归测试守护。

### III. 向后兼容优先

扩展函数签名用带默认值的新参数；旧调用路径行为逐字节不变。新增 JSON 字段只增不改。
`suggest_segments(duration_ms)` 旧签名必须永远等价于改动前——这是非协商回归门。

### IV. 可扩展模块化

新增一种"分类/策略/结构形态"只在一个注册表加一条 + 一组测试，不触碰核心流程
（prepare_merge / apply_merge / review_merge 核心逻辑）。注册表条目是纯数据，无行为分支。

### V. 复用优先，不重复造轮子

需要的能力若已在仓库存在则复用：PPT 翻页检测复用 video-to-slides 的 `detect_scene_changes`/`detect_slides`；
OCR 复用 `extract_text`；时间戳归一化复用 `normalize_raw`。新写前先 grep。

## 文档与语言

- 代码注释用中文；设计文档（spec/plan）用中文。
- Spec 写到 `docs/superpowers/specs/<YYYY-MM-DD>-<name>-design.md`；Plan 写到 `docs/superpowers/plans/<YYYY-MM-DD>-<name>.md`。
  spec-kit 的 `specs/NNN-.../` 用作工作流脚手架，spec 内容单一来源在 `docs/superpowers/specs/`（spec.md 软链过去）。
- 技术栈：Python 3.9+、pytest、json。Python venv 在 `.venv/`。

## 开发流程

- TDD：失败测试 → 实现 → 跑绿 → 每任务一次 commit。
- 跨技能改动（如 video-summary + video-to-slides 共享 `_shared/transcript_merge`）须跑全量相关测试。
- 既有测试必须全绿才可提交；改动 `suggest_segments` 类函数须跑 `test_transcript_merge.py::TestSuggestSegments` 回归。

## Governance

本 Constitution 高于其他实践；与既有计划（如 2026-07-01 review agent 计划）中"脚本只算约束"原则一致。
复杂度需证明；用 `[GUIDANCE_FILE]` 指向具体 spec/plan。
新增违反上述原则的设计必须在本 Constitution 记录修正案。

**Version**: 1.0.0 | **Ratified**: 2026-07-02 | **Last Amended**: 2026-07-02
