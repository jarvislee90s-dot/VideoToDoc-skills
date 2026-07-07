# Spec 对照报告（2026-07-07-video-to-slides-capture-and-matching-refactor.md）

**对照时间**：2026-07-07
**代码 commit**：d282b3d7（R2 修复后）
**端到端验证**：video-to-slides keep_all=False（21→21）+ keep_all=True（21→52），均通过

## 图例
- ✓ 完全实现
- ⚠ 部分实现（存在/可用但未贯穿）
- ✗ 未实现

## 逐条对照

### 4.1 严格度按 video_type 自动调 ⚠
| 需求 | 实现 | 状态 |
|------|------|------|
| `_scene_threshold_for_type` | slides.py:186 已存在，detect_slides 已在用 | ✓ |
| `_min_slide_seconds_for_type` | slides.py:197 已实现 | ✓ 函数 |
| `_max_candidates_for_type` | slides.py:208 已实现 | ✓ 函数 |
| **detect_slides 调用 `_min_slide_seconds_for_type`** | detect_slides:51 用 `settings.min_slide_seconds` 直传，**未调新函数** | ✗ |
| **detect_slides 调用 `_max_candidates_for_type`** | 候选点无硬上限，**未调** | ✗ |
| 端到端：video_type=tutorial → 理论 max=300 | tutorial 实际 51 候选（< 300），未触发 | — |

### 4.1.5 动态调整算法 ⚠
| 需求 | 实现 | 状态 |
|------|------|------|
| type_density 表（5 个 video_type） | **未实现** | ✗ |
| `estimated = duration_sec * type_density` | **未实现** | ✗ |
| `dynamic_min_slide` 动态放大公式 | **未实现**，用简化版 (duration/900) | ✗ |
| 边界保护 `min_slide_seconds ≤ duration * 0.5` | **未实现** | ✗ |
| 端到端：14min lecture_slides → 实际 336 候选 | 当前 51 候选（未触发边界）| — |

### 4.2 匹配窗口 [Y-W, Y) ⚠
| 需求 | 实现 | 状态 |
|------|------|------|
| `_match_window` 公式 `max(X, Y-W)` | slides.py 已实现 | ✓ |
| 边界回退（段长 < W → 全段）| 已实现 | ✓ |
| **per-type W 映射**（talking_head=8, lecture=3, screen=3, others=5）| 代码用 `settings.match_window_sec or 5` 单一值，**未做 per-type** | ✗ |
| SKILL.md 文档 per-type W | 已文档化 | ✓ |

### 4.3 段间抢图：天然不重叠 ✓
左闭右开天然处理，无需额外逻辑。已验证。

### 4.4 段内多候选 ✓
| 需求 | 实现 | 状态 |
|------|------|------|
| `keep_all_segment_candidates` 字段 | config.py 已加 | ✓ |
| 关闭模式：1 张主图 | trim 实现 | ✓ |
| 开启模式：N 张按时间顺序 | trim 实现 | ✓ |
| 端到端：keep_all=False → 21 sections | 验证通过 | ✓ |
| 端到端：keep_all=True → 52 sections（21 段平均 2.5 张）| 验证通过 | ✓ |

### 4.5 主图评分：edge + OCR 关键词 ✓
| 需求 | 实现 | 状态 |
|------|------|------|
| `score = α*edge_norm + β*ocr_overlap`，α=β=0.5 | `_score_candidate` | ✓ |
| edge 段内归一化 | `edge / max(max_edge_in_seg, 1e-6)` | ✓ |
| OCR 关键词 Jaccard | `_ocr_keyword_overlap` | ✓ |
| 字符 bigram 提取 | `_extract_keywords` | ✓ |
| OCR 空时 overlap=0.0 | `if not ocr_text: return 0.0` | ✓ |
| 评分最高者为主图 | `_pick_main_candidate` | ✓ |

### 4.6 图片命名 ✓（R2 修复后）
| 需求 | 实现 | 状态 |
|------|------|------|
| 格式 `p{NN}_{MM}_{X.Ys}[_main|_cand].png` | `_build_image_name` | ✓ |
| 主图加 `_main` | ✓ | ✓ |
| **候选加 `_cand`** | ✓（R2 修复） | ✓ |
| 单图无后缀 | ✓ | ✓ |
| 端到端：keep_all=True 产物 `p01_01_main_14.4s.png` | 验证通过 | ✓ |
| 端到端：候选 `p04_02_cand_89.2s.png` | 验证通过 | ✓ |
| 端到端：keep_all=False 单图 `p01_01_14.4s.png` | 验证通过 | ✓ |

### 4.7 文档展示 ✓
| 需求 | 实现 | 状态 |
|------|------|------|
| 紧凑版多图按时间顺序渲染 | `render_compact_markdown` | ✓ |
| 整理版 `<!-- IMAGE:N-M[:main] -->` 占位符 | `ensure_semantic_markdown` | ✓ |
| `is_main` 检测 | `"_main_" in stem` | ✓ |
| `restore_images` 兼容新+旧占位符 | 已更新 | ✓ |
| 单图回退 | `image_paths or [image_path]` | ✓ |

### 4.8 性能优化：opencv 批量截图 ⚠
| 需求 | 实现 | 状态 |
|------|------|------|
| `capture_frames_opencv` 函数 | slides.py 已实现 + 3 测试通过 | ✓ 函数 |
| **pipeline 实际使用 opencv 批量截候选** | pipeline 仍用 `extract_frame`（ffmpeg）| ✗ |
| `use_opencv_capture` 设置生效 | 设置存在但**未读取** | ✗ |
| `detect_workers` 并行截 | 设置存在但**未读取** | ✗ |

### 4.9 Settings 新增字段 ✓
9 字段全部存在，默认值与 spec 一致。

### 4.10 SKILL.md CLI 参数 ⚠
| 参数 | 状态 |
|------|------|
| `--scene-threshold` | ✓ 存在 |
| `--min-slide-seconds` | ✓ 新增 |
| `--max-candidates` | ✓ 新增 |
| `--match-window-sec` | ✓ 新增 |
| `--keep-all-candidates` | ✓ 存在 |
| `--no-opencv-capture` | ✓ 新增 |
| **`--detect-workers`** | ✗ **缺失**（Settings 有字段，CLI 未暴露）|

### 4.11 video_type 全参数映射表 ⚠
| 参数 | 文档（SKILL.md）| 代码实现 |
|------|----------------|----------|
| scene_threshold per-type | ✓ | ✓（detect_slides 在用）|
| **min_slide_seconds per-type** | ✓ | ✗（detect_slides 用 settings 直传）|
| **max_candidates per-type** | ✓ | ✗（未调用 `_max_candidates_for_type`）|
| **match_window_sec per-type** | ✓ | ✗（用单一值 or 5）|

## 端到端验证

### video-summary 产物
- audio.wav 28MB ✓
- transcript_merged.json 21 段 ✓
- merge_review_report.json ✓

### video-to-slides keep_all=False
- 21 sections（21 段每段 1 张）✓
- 单图命名 `p{NN}_{01}_{X.Ys}.png` 无后缀 ✓
- capture_ms 保留原始值 ✓

### video-to-slides keep_all=True
- 52 sections（21 段平均 2.5 张）✓
- 主图 `p{NN}_{MM}_main_{X.Ys}.png` ✓
- 候选 `p{NN}_{MM}_cand_{X.Ys}.png` ✓（R2 修复后）
- 语义名经 materialize 保留 ✓

## Spec 完成度汇总

| 类别 | 数量 |
|------|------|
| ✓ 完全实现 | 4.3, 4.4, 4.5, 4.6, 4.7, 4.9（6 项）|
| ⚠ 部分实现 | 4.1, 4.1.5, 4.2, 4.8, 4.10, 4.11（6 项）|
| ✗ 未实现 | 0（所有 spec 需求至少有部分代码）|

**未贯穿的关键点**（6 处）：
1. **G1**: detect_slides 不调 `_min_slide_seconds_for_type`
2. **G2**: detect_slides 不调 `_max_candidates_for_type`（候选无硬上限）
3. **G3**: 4.1.5 动态调整算法未实现（简化版）
4. **G4**: match_window_sec 无 per-type 映射
5. **G5**: CLI 缺 `--detect-workers`
6. **G6**: opencv 未被 pipeline 实际使用（use_opencv_capture / detect_workers 未读取）
