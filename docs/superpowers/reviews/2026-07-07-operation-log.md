# 操作日志：video-to-slides 图文对齐修复 + video-type 分流

**日期**：2026-07-07
**目标**：执行 spec + plan → 代码审查 → 端到端测试 → 操作日志
**总耗时**：约 17 分钟（00:18 - 00:35）

## 一、执行计划（8 个任务）

按 TDD 流程逐任务实现：写测试 → 验证红 → 实现 → 验证绿 → commit。

| 任务 | 内容 | 耗时 | commit |
|------|------|------|--------|
| 1 | classify_video 视频类型自动分类 | ~1min | `124a709c` |
| 2 | --video-type 参数（config/cli/process） | ~1min | `3acc06f5` |
| 3 | trim 段落主导改造（核心修复） | ~1min | `7909d6bd` |
| 4 | detect_slides 按类型调场景阈值 | ~30s | `c4e423db` |
| 5 | align 段主导回归测试 | ~30s | `8d35aaac` |
| 6 | pipeline 串联 classify_video | ~1min | `22d4c620` |
| 7 | 文档修复（4 处卡点） | ~1min | `da264170` |
| 8 | 全量测试（110 pass） | ~1min | — |

### 适配说明

spec/plan 中 `_sample_frames_for_classify` 使用 `av`（PyAV）采样帧，但 `.venv` 未安装 `av`。改用 `cv2.VideoCapture`（已安装），`_compute_scene_rate` 用已有的 `probe_duration_ms` 替代 `av` 取时长。无新依赖引入。

## 二、代码审查

| 检查项 | 结果 |
|--------|------|
| 核心 bug 修复正确性 | 通过——trim 用段边界，capture=段末-500 |
| 纯函数设计 | 通过——_classify_by_features / _scene_threshold_for_type |
| 向后兼容 | 通过——auto 时阈值=base，行为不变 |
| 防御性编程 | 通过——dhash/edge_density try/except |
| PEP8 | 修复——补空行、移除未用 import |
| 低风险残留 | 3 项（缓存键不含 video_type / image_to_seg 死代码 / classify 耗时 5-10s） |

审查报告：`docs/superpowers/reviews/2026-07-07-video-to-slides-alignment-code-review.md`

## 三、端到端测试

### 测试视频

BV1MAUsBME6f — 「文字为啥非得向量化？嵌入矩阵中隐藏的真理【白话Transformer02】」
时长 620s，239 ASR 碎句。

### 执行流程

| 步骤 | 耗时 | 结果 |
|------|------|------|
| video-summary 下载 + ASR | ~3min | 退出码 0，239 段 |
| 阶段 0：prepare_merge | <1s | 239 碎句 → 建议 31 段 |
| 阶段 0：Agent 合并 | ~1min | 25 段 merged_groups.json |
| 阶段 0：apply_merge + review + check | <1s | 0 critical，3 warning，闸口通过 |
| 阶段 1：process.py（截图+对齐） | ~3min | 22 页，3 份 Markdown |

### 视频类型判定

```
scene_rate=0.0728  edge=0.0294  sat=27.1  → tutorial
```

判定合理：场景变化适中（非 talking_head 的 <0.03），边缘密度低（非 lecture_slides 的 >0.15），饱和度低。tutorial 用 base 阈值 0.06。

### 核心验证：段末对齐率

| 方法 | 对齐率 | 说明 |
|------|--------|------|
| 按首段索引（quickstart 脚本） | 86% (19/22) | 3 页跨多段时首段≠capture 段 |
| 按末段索引（正确逻辑） | **100% (22/22)** | capture 精确 = 段末 - 500ms |

**旧版仅 26% (10/39)**，修复后 100%。所有 22 页 capture_ms 均精确等于 para_end - 500ms。

> 注：quickstart 验证脚本用 `segment_indexes[0]` 取首段索引，当一页跨多段（align 归并无图段）时首段≠capture 所在段。正确做法是取 `segment_indexes[-1]`（末段索引）。

### bug 点回归检查

| # | 卡点 | 验证 | 结果 |
|---|------|------|------|
| 1 | video-summary 命令路径 | `grep -c "python3 scripts/process.py" SKILL.md` = 0 | 已修复 |
| 2 | B站 v_voucher 风控 | cookies 回退下载成功 | 通过 |
| 3 | browser_cookie3 缺失 | 不影响回退 | 通过 |
| 4 | merge_procedure 路径重复 | `grep -c "videotodoc/videotodoc"` = 0 | 已修复 |
| 5 | 整理版缺 ## 图文讲义 | 生成文件 0 匹配，SKILL.md 已说明 Agent 须补 | 一致 |
| 6 | review_agent_prompt 归属 | `grep -c "video-summary 步骤"` = 0 | 已修复 |
| 7 | shell f-string | 使用技巧，非代码 bug | N/A |
| 8 | grep -c 退出码 | 使用技巧，非代码 bug | N/A |
| 9 | 图文对齐错位 | 22/22 = 100% | 已修复 |

## 四、产物清单

| 产物 | 路径 |
|------|------|
| Spec | `docs/superpowers/specs/2026-07-07-video-to-slides-alignment-fix-design.md` |
| Plan | `docs/superpowers/plans/2026-07-06-video-type-talking-head-alignment.md` |
| Quickstart | `specs/002-video-to-slides-alignment/quickstart.md` |
| 代码审查 | `docs/superpowers/reviews/2026-07-07-video-to-slides-alignment-code-review.md` |
| 操作日志 | `docs/superpowers/reviews/2026-07-07-operation-log.md` |
| 测试视频 run | `runs/文字为啥非得向量化？..._20260707_002712/` |

## 五、变更统计

- 14 文件，+400/-64 行
- 9 个 commit
- 17 个新增测试（总计 110 全绿）
- 0 个新依赖引入
