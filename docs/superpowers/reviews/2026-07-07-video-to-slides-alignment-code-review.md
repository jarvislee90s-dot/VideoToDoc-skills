# 代码审查：video-to-slides 图文对齐修复 + video-type 分流

**审查范围**：`a7688abc..HEAD`（7 个 commit，14 文件，+400/-64 行）
**审查日期**：2026-07-07

## 变更概览

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `slides.py` | 核心 | +VideoType、classify_video、_scene_threshold_for_type、trim 段落主导 |
| `config.py` | 配置 | +video_type 字段 |
| `cli.py` | CLI | +--video-type 参数 |
| `process.py` | 入口 | +--video-type 透传 |
| `pipeline.py` | 编排 | capture_video + process_video 调 classify_video |
| `test_video_type.py` | 新增 | 9 测试（分类 + 阈值） |
| `test_frame_selection.py` | 修改 | +2 测试（段边界 + talking_head 取帧） |
| `test_align.py` | 修改 | +2 测试（段主导对齐回归） |
| `test_cli.py` | 修改 | +2 测试（video_type 参数） |
| `test_pipeline_transcript.py` | 修改 | +2 测试（auto classify 写回） |
| 4 个文档 | 修复 | 命令路径/归属/标题说明 |

## 审查结论：通过

### 正面发现

1. **核心 bug 修复正确**：`trim_candidates_by_transcript` 改为用 transcript 段边界做 slide.start/end_ms，capture_ms = 段末 - margin。根因（用候选图窗口做段时间范围）被精准定位和修复。
2. **纯函数设计**：`_classify_by_features` 和 `_scene_threshold_for_type` 是纯函数，无副作用，易于单测。9 个测试覆盖所有类型边界。
3. **向后兼容**：`video_type="auto"` 时 `_scene_threshold_for_type` 返回 base，行为完全不变。现有 110 个测试全绿。
4. **防御性编程**：talking_head 段末取帧的 dhash/edge_density 加了 try/except，避免帧提取失败导致崩溃。
5. **适配合理**：av 不可用时改用 cv2.VideoCapture，复用 detect_scene_changes + probe_duration_ms，未引入新依赖。

### 低风险残留

1. **缓存键不含 video_type**：`slides_slug` 用 `settings.scene_threshold` 而非 type-adjusted threshold。auto 时同一视频分类结果固定，无影响；显式切换 `--video-type` 时需 `--force-rebuild slides`。可接受。
2. **image_to_seg 死代码**：`trim_candidates_by_transcript` 中 `image_to_seg` dict 构建后未读取。属预存代码，注释已说明为何不需要。不在本次范围内。
3. **classify_video 耗时**：采样 30 帧 + detect_scene_changes（ffmpeg 全片扫描）增加 5-10s。capture 阶段一次性开销，可接受。

### 测试覆盖

| 维度 | 测试数 | 状态 |
|------|--------|------|
| 分类纯函数 | 6 | 通过 |
| 阈值映射 | 3 | 通过 |
| trim 段边界 | 2 | 通过 |
| align 段主导 | 2 | 通过 |
| cli 参数 | 2 | 通过 |
| pipeline auto | 2 | 通过 |
| 现有回归 | 93 | 通过 |
| **合计** | **110** | **全绿** |
