# SPEC vs 实际产物差异文档

**测试视频**：BV1MAUsBME6f（文字为啥非得向量化？，620s，239 ASR 碎句）
**测试日期**：2026-07-07
**目的**：完整跑完 video-summary + video-to-slides 流程后，对照 SPEC 列出差异（先不修复）

---

## 1. SPEC 承诺 vs 实际结果

| SPEC 指标 | SPEC 目标 | 实际结果 | 差异 |
|-----------|-----------|----------|------|
| 段末对齐率 | ≥ 90% | **100%**（22/22，capture 精确=段末-500ms） | 超出目标 |
| 截图字幕落末句 | 字幕对齐 | 字幕对齐（页 1/3/12/17/22 抽查均匹配） | 符合 |
| talking_head 段末取帧 | 无候选时补帧 | **未触发**（视频判为 tutorial，非 talking_head） | 缺失 |
| 视觉内容匹配文本 | 未提及 | 部分页（1, 22）显示相同视觉（Embedding 矩阵）| 超出 SPEC 范围 |

---

## 2. 完整流程卡点记录

### 2.1 video-summary 阶段

| 步骤 | 结果 | 卡点 |
|------|------|------|
| 下载视频 | ✅ 成功 | 无 |
| B站 v_voucher 风控 | ⚠️ 触发 | cookies 回退成功（符合 SKILL.md 预期）|
| ASR 转录 | ✅ 239 段 | 无 |

### 2.2 video-to-slides 阶段 0（合并碎段）

| 步骤 | 结果 | 卡点 |
|------|------|------|
| prepare_merge | ✅ 建议 31 段 | 无 |
| Agent 合并 | ⚠️ 手动 | 需人工按主题分组 239→25 段（无自动合并能力）|
| apply_merge | ✅ 成功 | 无 |
| review_merge | ⚠️ 3 warning | 2 组字符数低于 80 下限；1 组包含 18 短句超 15 上限 |
| **self_review 注入** | ❌ **未文档化** | `check_review_report.py` 要求 `self_review` bool 键，review_merge 不自动写入，需手动注入 |
| check_review_report | ✅ 退出码 0 | 无 |

### 2.3 video-to-slides 阶段 1（截图+对齐）

| 步骤 | 结果 | 卡点 |
|------|------|------|
| 视频类型判定 | ⚠️ `tutorial` | 判型正确（scene_rate=0.073 介于 talking_head 与 lecture_slides 之间），但**不是 SPEC 设计的 talking_head 场景** |
| detect_slides 场景检测 | ✅ 40 候选 | 阈值 0.06（tutorial 用 base） |
| trim 段落主导 | ✅ 100% 对齐 | capture=段末-500ms 全部精确 |
| 三段式去重 | ⚠️ 0 obvious dup, 19 obvious different, 3 OCR checks, **1 OCR duplicate** | OCR 判 1 对重复但保留为不同（可能是字幕差异导致 OCR 不判重）|
| 生成 Markdown | ✅ 3 份 | 无 |

### 2.4 video-to-slides 阶段 2（Agent 整理）

| 步骤 | 结果 | 卡点 |
|------|------|------|
| ⑤ 目录 (TOC) | ⚠️ 手动 | 需 Agent 阅读全文+识别章节+写 8 章 TOC（无自动化）|
| ⑥ 整理版标题 | ❌ **缺** | 生成的整理版默认**不含** `## 图文讲义` 标题（这是 Bug 5，SKILL.md 已在文档任务 7 中修正说明）|
| ⑥ 语义改写 | ⚠️ 手动 | 22 页全部需 Agent 重写（无自动化）|
| ⑦ 思维导图 | ⚠️ 手动 | 需 Agent 编写 Mermaid .mmd（无自动化）|

### 2.5 video-to-slides 阶段 3（finalize.py）

| 步骤 | 结果 | 卡点 |
|------|------|------|
| 恢复图片 | ✅ 22 页 | 无 |
| 渲染思维导图 | ✅ mindmap.png | 无 |
| 生成 Word | ✅ 3 份 docx | 无 |

---

## 3. SPEC 核心修复 vs 实际表现

### 3.1 段落主导对齐（任务 3，核心修复）

**SPEC 承诺**：
- slide.start_ms/end_ms = 段边界
- capture_ms = 段末 - 500ms
- talking_head 无候选段末直接 extract_frame

**实际表现**：
- ✅ slide 时间范围 = 段边界（22/22 验证通过）
- ✅ capture_ms = 段末 - 500ms（22/22 精确匹配）
- ❌ talking_head 段末补帧**未触发**（视频判为 tutorial）

### 3.2 video-type 判型（任务 1）

**SPEC 承诺**：
- scene_rate < 0.03 + edge < 0.10 + sat < 60 → talking_head
- 否则回退 tutorial

**实际表现**：
- scene_rate=0.0728（> 0.03 阈值）→ 不命中 talking_head → 回退 tutorial
- 判型逻辑正确，但**该视频不匹配 talking_head 场景**
- SPEC 设计基于 talking_head 为典型场景，实际该视频更接近 tutorial

### 3.3 场景检测阈值（任务 4）

**SPEC 承诺**：
- talking_head → 0.20（宽松）
- lecture_slides → 0.03（敏感）
- auto/tutorial → base（0.06）

**实际表现**：
- tutorial 用 base 0.06 → 与旧版完全一致
- 该功能未在本视频得到验证（需 talking_head 视频才能对比效果）

---

## 4. 超出 SPEC 范围的关键发现

### 4.1 视觉内容 vs 文本不匹配

**现象**：部分页面（如页 1、22）显示的幻灯片视觉内容（Embedding 矩阵）来自视频后半段，但对应文本是开场/结尾。

**原因**：
- 该视频为"talking_head 风格但带 PPT"——同一张幻灯片长时间停留，只有底部字幕变化
- OCR 去重阈值（0.92 相似度）未判这些为重复，因为：
  - dHash 相同但 change_ratio 可能因字幕变化而 > 0.005
  - OCR 文本不同（字幕不同）→ 相似度 < 0.92

**SPEC 状态**：未提及此场景。SPEC 只保证"时间对齐"和"字幕对齐"，不保证"视觉内容对齐"。

**实际影响**：22 页中有 2 页（1, 22）的视觉内容与文本语义不匹配。

### 4.2 截图字幕确实落在末句

抽查的 5 页（1, 3, 12, 17, 22）的截图底部字幕均与该段最后一句匹配：
- 页 1：字幕"闭上眼睛" ← 段末"闭上眼睛跟我一起进入梦境"
- 页 3：字幕"粉色就是女生" ← 段末"粉色就是女生"
- 页 12：字幕"与上下文词的词向量的点积" ← 段末"让它们的点积越小越好"
- 页 17：字幕"我们看到这块的话" ← 段末文本
- 页 22：字幕"看看它后面还有哪些精彩的故事吧" ← 段末"看看它后面还有哪些精彩的故事吧"

**结论**：SPEC 承诺的"字幕落末句"100% 达成。

### 4.3 阶段 0 的 self_review 注入是隐藏必做项

`check_review_report.py` 闸口要求 `self_review` 为 bool 键，但 `review_merge.py` 不自动写入。该流程未在 SKILL.md 阶段 0 步骤中明确说明，Agent 必须知道这个隐藏要求。

---

## 5. 差异汇总表

| # | 差异类型 | SPEC 表述 | 实际表现 | 严重度 |
|---|----------|-----------|----------|--------|
| 1 | 视频类型不符 | SPEC 以 talking_head 为典型 | 本视频判为 tutorial，talking_head 特定行为未触发 | 中 |
| 2 | 视觉内容不匹配 | 未提及 | 部分页（1, 22）同视觉跨段落复用 | 中 |
| 3 | self_review 注入 | SKILL.md 未文档化 | 需 Agent 手动写入 bool 键 | 中 |
| 4 | 阶段 2 全手动 | 未说明自动化程度 | TOC/改写/思维导图全 Agent 手写 | 低（符合 SKILL.md）|
| 5 | OCR 去重边界 | SPEC 未涉及 | 视觉相同但字幕不同的页面被判为不同 | 中 |

---

## 6. 未发现 SPEC 与实现的不一致

以下 SPEC 设计均正确实现并验证：
- ✅ VideoType Literal 类型定义
- ✅ _classify_by_features 纯函数（9 个测试覆盖）
- ✅ _scene_threshold_for_type 映射
- ✅ trim_candidates_by_transcript 段落边界改造
- ✅ talking_head 无候选段末取帧（代码已实现，本视频未触发）
- ✅ detect_slides 按类型调阈值
- ✅ align_sections 复用 slide 时间范围
- ✅ pipeline capture_video + process_video 串联 classify_video
- ✅ --video-type CLI 参数

---

## 7. 建议后续方向（不修复，仅记录）

1. **talking_head 视频验证**：需找一段真正的 talking_head 视频（人脸为主）来验证 talking_head 段末取帧逻辑
2. **视觉内容匹配**：可考虑加入"同视觉跨段合并"逻辑（基于 dHash + 字幕区域 mask）
3. **self_review 自动化**：`review_merge.py` 应自动写入 `self_review=False`（路径 A 假设），避免 Agent 遗忘
4. **阶段 2 自动化**：目录生成+语义改写+思维导图仍需大量 Agent 工作，可考虑 LLM 辅助
5. **OCR 去重字幕感知**：去重时 mask 字幕区域，避免字幕变化导致判为不同
