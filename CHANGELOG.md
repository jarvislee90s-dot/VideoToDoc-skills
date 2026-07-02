# Changelog

本项目所有重要变更记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## 2026-07-02

### Added

- **video-summary 转录合并支持结构形态原型分段策略**：4 个原型（`topic_preserve` 话题保完整 / `enumeration_unit` 枚举按单元 / `visual_event` 视觉事件 / `rescan_grid` 全文重组）注册在可扩展的 `STRATEGY_REGISTRY`，`suggest_segments(duration_ms, archetype, visual_signals)` 按原型套不同柔性区间；旧单参签名逐字节等价（向后兼容，非协商回归门）
- `signal_stats.py`：纯统计提示（各原型锚点词命中计数），**不决策**——类型判定归 agent（三层证据：L1 用户先验 / L2 标题摘要 / L3 全文权威）
- `prepare_merge.py` 新增 `--archetype` / `--force-archetype` / `--visual-signals` / `--tid`；原型③翻页边界复用 video-to-slides 的 `slides.json`（同 run_dir 自动探测），缺信号降级 `visual_missing` warning 不崩
- video-to-slides `SKILL.md` 增加完整工作流图示（mermaid 流程图，含前置 video-summary 与后续发布闭环）
- 补充 6-7 月设计文档（`docs/superpowers/specs|plans`，含本期分段策略设计）与 spec-kit 脚手架（`specs/001-.../`、`.specify/memory/constitution.md` 项目宪法）
- 初赛 Demo 资产更新（`docs/trae-competition/` 内嵌数据、截图、预览页）

### Changed

- video-summary `SKILL.md` 合并步骤前增加"原型判定"（4 原则 + 三层证据 + ③翻页/降级 + 区域级混合 + `--force-archetype` 逃生舱 + L1/L3 冲突报告）
- 更新 README 目录结构与特性说明
- 测试增至 59 例（新增 strategies / signal_stats / prepare_merge + Constitution III 字节等价回归门 + review_merge 原型区间）

## 2026-07-01

- 新增 TRAE 初赛 Demo HTML，支持 Agent 对话回放、三列节点执行流可视化、真实 SpaceX 产物展示

## [0.3.0] - 2026-06-30

### Changed

- 思维导图渲染从 Pillow 手绘目录树布局改为 Mermaid CLI (`mmdc`) 的 `tidy-tree` 布局
- 移除 `--mermaid` 参数，Mermaid 渲染成为唯一渲染方式
- 1 级章节标题自动添加序号（如 `1. 基础概念`）
- 思维导图不再按章节拆分为多张 PNG，统一输出单张 `<视频标题>_思维导图_<时间戳>.png`
- 移除 Python 布局引擎 `mindmap_layout.py`、校验模块 `mindmap_verify.py` 及对应测试

### Added

- 新增 `mindmap_mermaid.py`：`.mmd` 预处理（`tidy-tree` frontmatter、章节序号）
- 新增 `test_mindmap_mermaid.py`、`test_mindmap_render.py`、`test_mindmap_verification.py` 覆盖 Mermaid 渲染链路

## [0.2.0] - 2026-06-18

### Changed

- 核心架构从"截图驱动分段"改为"分段驱动截图"
- 候选点生成（`_candidate_points`）：固定间隔决定候选点数量，场景变化点仅在间隔窗口内微调 capture_ms，不再产生额外候选点
- 分段草案（`generate_pending_segments`）：由 transcript 内容密度驱动分段边界，合并到 `max_segment_chars` 上限，不再由候选图 capture_ms 决定
- finalize（`finalize_segment_slides`）：每段选 1 张 edge_density 最高的截图，slide 时间范围设为段 [start_ms, end_ms]，不再段内多图
- 飞书发布：合并 title + body + divider 为一次 append 调用，API 调用从 4N 降到 2N+1

### Fixed

- B站 412 反爬：新增 `--cookies-from-browser` 参数（chrome/firefox/safari/edge），`_bilibili_download` 复用已获取的流 URL 不再重复请求 playurl
- SRT/VTT 时间戳解析：`_parse_subtitle_file` 解析 `-->` 时间戳行为 start_ms/end_ms，`save_subtitle_as_transcript` 保存为 `{segments, language}` dict 格式
- `python3 -m videotodoc` 报错：添加 `__main__.py` 入口
- 飞书发布无进度输出：每页发布后 `print(..., flush=True)`
- merge 段时间范围未扩展到目标段：新增 `_apply_merge_extensions`，finalize 读取 confirmed_segments 后扩展 merge 段的 end_ms 和 candidate_slide_ids

### Results

- 22 分钟视频候选图数：110 → 45
- 最终页数：100 → 22
- 单元测试：19 → 41 全部通过

## [0.1.0] - 2026-06-17

### Added

- 时长密度函数：根据视频时长动态决定截图间隔（≤5min→15s，≤15min→20s，≤30min→30s，>30min→40s）
- 中断式 pipeline：capture → review-segments → finalize 三步分离，支持 agent 介入分段
- 分段草案启发式 + confirmed 格式校验
- pytest 测试基础设施
- 飞书 publish.py v2 适配 + 重试 + 断点续传
- B站 v_voucher 风控分层探测
