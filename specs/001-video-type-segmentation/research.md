# Phase 0 研究：视频类型→转录分段策略

> 所有技术未知已在调研中确认，无残留 NEEDS CLARIFICATION。

## 1. Python 3.9 兼容写法

**Decision**：沿用仓库既有写法 `from __future__ import annotations`，类型注解用字符串形式（`dict | None` 在注解位置因 future import 被当成字符串，3.9 安全）。运行期类型用 `Optional[dict]` 或 `dict | None`（后者仅注解）。

**Rationale**：`.agents/skills/_shared/transcript_merge/__init__.py` 第 6 行已有 `from __future__ import annotations`，沿用零风险。本机 `.venv` 是 3.14.4 但代码目标 3.9+。

**Alternatives**：纯 `Optional`/`Union` —— 更啰嗦，否决。

## 2. video-to-slides 的视觉信号 API

**Decision**：原型③直接调用 `video-to-slides/videotodoc/slides.py::detect_scene_changes(video_path, threshold) -> list[int]`（返回场景切换 ms 列表）与 `detect_slides(...) -> SlideSet`（Slide 带 `start_ms/end_ms/ocr_text`）。

**Rationale**：已核实源码（`grep` 确认函数签名），复用 Constitution V，不重写帧差/OCR。`detect_scene_changes` 是纯函数式入口，返回值即 `slide_boundaries_ms` 所需。

**Alternatives**：自写帧差 —— 违反 Constitution V，否决。

## 3. signal_stats 信号词表来源

**Decision**：词表内嵌在 `signal_stats.py` 常量，分 4 组对应 4 原型锚点（topic_transition/enumeration/visual_hint/grid_markers）。仅计数，不分类。

**Rationale**：词表是"提示"非"分类器"，Constitution I 要求脚本不决策——所以不需要训练/阈值，词表越简单越好，agent 自行语义判定。词表可后续扩展。

**Alternatives**：调 LLM 分类 —— 违反"不调大模型做分类"，否决。

## 4. merge_input.json 向后兼容

**Decision**：新增 `archetype` + `strategy` + 可选 `visual_signals` 字段，旧字段不变。review_merge.py 读 `suggestion` 区间逻辑不变，新字段对它透明。

**Rationale**：Constitution III（新增字段只增不改）。已核实 `review_merge.py` 只读 `suggestion.per_group_range`/`chars_per_group_range`，新增字段不影响。

## 5. 三层证据的 L2 是否调 LLM

**Decision**：L2（标题+摘要）不单独调 LLM。L2 价值有二：①纯规则关键词预启视觉信号（标题含"PPT/课件"则预启翻页检测，非 LLM）；②作为 L3 agent 的上下文。权威判定归 L3。

**Rationale**：避免为前期判断多调一次大模型；L3 全文判定最准。

**Alternatives**：L2 调 LLM —— 成本高且 L3 已覆盖，否决。
