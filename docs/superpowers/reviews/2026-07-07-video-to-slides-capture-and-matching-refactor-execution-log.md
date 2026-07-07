# video-to-slides capture-and-matching 重构 执行日志

**执行日期**：2026-07-07
**执行者**：Codex（子智能体驱动开发纪律 + 自审）
**计划**：[2026-07-07-video-to-slides-capture-and-matching-refactor.md](/Users/jarvis/Documents/VideoToDoc-skills/docs/superpowers/plans/2026-07-07-video-to-slides-capture-and-matching-refactor.md)
**分支**：`feat/step6-extract-to-video-to-slides`

---

## 1. 执行概览

| 指标 | 值 |
|------|---|
| 计划任务数 | 11（10 实现 + 1 端到端验证） |
| 实际完成 | 11/11 |
| 单元测试基线 | 214 passed |
| 单元测试最终 | **256 passed**（新增 42，无回归） |
| Commit 数 | 11（10 实现 + 1 文档） |
| 端到端验证 | keep_all=False 21→21 / keep_all=True 21→52 |

---

## 2. 任务逐项记录

### 任务 1：Settings 新增 9 字段 ✅
- **文件**：`config.py` + `tests/test_config_settings.py`
- **实现**：`min_slide_seconds` 改 1.0（从 1.5）；新增 `max_candidates` / `match_window_sec` / `keep_all_segment_candidates` / `main_score_edge_weight` / `main_score_ocr_weight` / `use_opencv_capture` / `detect_workers`
- **测试**：1 passed
- **Commit**：`129acf3c`
- **偏差**：无

### 任务 2：`_min_slide_seconds_for_type` + `_max_candidates_for_type` ✅
- **文件**：`slides.py` + 两个测试文件
- **实现**：按 video_type 映射最小换页点；按 type_cap + duration_factor 算候选上限
- **测试**：10 passed
- **Commit**：`4d19cc04`
- **偏差**：`duration_factor` 用 `duration_sec / 900.0`（计划文档写 1800）。原因：1800 时 lecture_slides(60min) 得 400 而非测试期望 500；movie_cinematic(60min) 得 400 而非 800。900 使 scaled_base ≥ type_cap，min 取到 type_cap。语义：每 15 分钟候选数翻倍，达上限即封顶。

### 任务 3：`_match_window` ✅
- **文件**：`slides.py` + `tests/test_match_window.py`
- **实现**：`[max(seg_start, seg_end - W), seg_end)` 左闭右开
- **测试**：4 passed
- **Commit**：`ebfa7080`
- **偏差**：无

### 任务 4：`_extract_keywords` + `_ocr_keyword_overlap` ✅
- **文件**：`slides.py` + `tests/test_score_candidate.py`
- **实现**：字符 bigram 集合 + Jaccard 重叠比
- **测试**：7 passed
- **Commit**：`0e33fdbb`
- **偏差**：无

### 任务 5：`_score_candidate` + `_pick_main_candidate` ✅
- **文件**：`slides.py`（追加测试到 `test_score_candidate.py`）
- **实现**：`edge_weight * edge_normalized + ocr_weight * ocr_keyword_overlap`；`max(slides, key=score)`
- **测试**：12 passed（任务 4 的 7 + 本任务 5）
- **Commit**：`89661072`
- **偏差**：无

### 任务 6：`_build_image_name` ✅
- **文件**：`slides.py` + `tests/test_image_naming.py`
- **实现**：`p{NN}_{MM}[_main]_{X.Ys}.png` 格式
- **测试**：3 passed（初次实现失败 1 个，修正 `_main` 位置后通过）
- **Commit**：`7695aeda`
- **偏差**：`_main` 置于秒数前（`p06_02_main_185.8s`）而非计划实现文档写的 `s` 后。计划测试期望 `_main` 在秒数前，测试是契约。

### 任务 7：`capture_frames_opencv` ✅
- **文件**：`slides.py` + `tests/test_capture_frames_opencv.py`
- **实现**：`cv2.VideoCapture` 一次打开多次 read，mp4v 测试视频 3 个测试全过
- **测试**：3 passed
- **Commit**：`2c23677f`
- **偏差**：`import cv2` 放在函数内（与 `_mean_saturation` / `_edge_density_from_array` 现有模式一致），未按计划加顶层 import。

### 任务 8：Section 扩展 + trim 改造 ✅
- **文件**：`models.py`（Section 加 `image_paths`）+ `slides.py`（重写 `trim_candidates_by_transcript`）+ 两个测试
- **实现**：`keep_all=True` 段内全部候选按时间顺序保留；`keep_all=False` 优先 [Y-W, Y) 窗口、窗口空时回退全段；保留原始 `capture_ms`（不再覆盖为段末-margin）；主图加 `_main` 标记
- **测试**：3 passed（任务 8 自身）+ 全量 250 passed
- **Commit**：`f9f7b24c`
- **偏差**（3 处计划与测试矛盾，已修正实现）：
  1. `keep_all=True` 计划实现用窗口过滤后只剩 1 张，测试期望保留段内全部 3 张 → 改用全段过滤
  2. 计划实现用 `end_capture_ms` 覆盖 `capture_ms`，测试期望保留原始值 → 不覆盖
  3. `keep_all=False` 窗口过滤后无候选时旧测试期望回退全段 → 加全段回退
  4. 更新 `test_frame_selection.py` 中 `test_slide_time_range_uses_segment_boundary` 断言从 `22000-500` 改为 `15000`（原始候选 capture_ms）

### 任务 9：紧凑版/整理版多图展示 ✅
- **文件**：`document.py`（两个函数重写）+ `restore_images.py`（占位符兼容）+ `tests/test_multi_image_markdown.py`
- **实现**：`render_compact_markdown` 循环渲染多图；`ensure_semantic_markdown` 生成 `<!-- IMAGE:N-M[:main] -->` 占位符；`restore_images` 兼容新旧两种占位符
- **测试**：3 passed
- **Commit**：`0ac2e7fd`
- **偏差**：`is_main` 检测用 `"_main_" in stem`（计划文档写 `stem.endswith("_main")`）。原因：命名格式 `p06_02_main_185.8s.png` 的 stem 不以 `_main` 结尾。

### 任务 10：CLI 参数透传 + SKILL.md ✅
- **文件**：`cli.py`（process subparser + settings 映射）+ `process.py`（参数 + cmd 透传）+ `SKILL.md`（参数表 + 多图说明）+ `tests/test_cli_new_args.py`
- **实现**：新增 `--max-candidates` / `--match-window-sec` / `--min-slide-seconds` / `--no-opencv-capture`；`--keep-all-candidates` 联动设置 `keep_all_segment_candidates = True`
- **测试**：3 passed
- **Commit**：`1cc552e2`
- **偏差**：无

### 任务 11：端到端验证 ✅
- **视频**：BV1ojfDBSEPv（15min，tutorial，21 段）
- **keep_all=False**：21 段 → 21 张图，每段 1 张主图，capture_ms 保留原始值
- **keep_all=True**：21 段 → 52 张图，平均每段 2.5 张，`keep_all_segment_candidates: True` 标记正确
- **视觉抽查**：首页 0001.png 为 Agent 概念讲解幻灯片（智能体架构 + 代码 + 对话气泡），质量合格
- **Commit**：`b5192d8e`（卡点文档更新 §9）

---

## 3. 计划偏差汇总

| 任务 | 偏差 | 原因 |
|------|------|------|
| 2 | `duration_factor` 用 900 而非 1800 | 1800 时 lecture_slides(60min) 得 400 ≠ 测试期望 500 |
| 6 | `_main` 置于秒数前 | 测试期望 `p06_02_main_185.8s.png`，计划实现文档有误 |
| 7 | `import cv2` 局部而非顶层 | 与现有 `_mean_saturation` 等局部 import 模式一致 |
| 8 | 3 处实现修正 | 测试与实现文档矛盾，测试是契约 |
| 9 | `is_main` 用 `"_main_" in stem` | 命名格式 stem 不以 `_main` 结尾 |
| 11 | B7 → Bug #1 标记 | 计划引用"B7"在文档中为不同 issue，实际重构改进的是 Bug #1（视觉跨段） |

---

## 4. 残余风险

1. **Bug #1 部分改进**：keep_all=True 给用户多候选选择，但**未做**自动跨段判定（OCR 关键词回退/前向回溯）。严重度从"高"降为"中"。
2. **`image_paths` 字段未自动填充**：pipeline align 阶段未把多张 trim slide 归组到 `Section.image_paths`（计划范围外）。文档渲染有 `or [image_path]` 回退，单图场景不受影响。
3. **图片命名被覆盖**：`materialize_selected_slides` 步骤将 `p{NN}_{MM}_{X.Ys}.png` 重命名为 `0001.png` 顺序编号。trim 的新命名仅在 trim 阶段目录（`slides_*`）生效，最终 selected_slides 用顺序编号。
4. **未触及 Bug #2/3/4/5**：视频风格干扰和 ASR 质量不在本次重构范围。

---

## 5. 完整 Commit 链

```
129acf3c feat(config): add 9 settings fields for capture-and-matching refactor
4d19cc04 feat(slides): add _min_slide_seconds_for_type and _max_candidates_for_type
ebfa7080 feat(slides): add _match_window for segment match window [Y-W, Y)
0e33fdbb feat(slides): add _extract_keywords and _ocr_keyword_overlap
89661072 feat(slides): add _score_candidate and _pick_main_candidate
7695aeda feat(slides): add _build_image_name with p{NN}_{MM}[_main]_{X.Ys} format
2c23677f feat(slides): add capture_frames_opencv for batch capture (5-10x speedup)
f9f7b24c refactor(slides): rewrite trim with [Y-W, Y) window + keep_all + main image
0ac2e7fd refactor(document): multi-image markdown with time-order and main marker
1cc552e2 feat(cli+skill): add 5 new params + keep_all doc + opencv mention
b5192d8e docs: mark capture-and-matching refactor as implemented (addresses Bug #1)
```

---

## 6. 验证命令

```bash
# 全量单元测试
.venv/bin/python3 -m pytest -q
# 256 passed in ~3.3s

# 端到端 keep_all=False
.venv/bin/python3 .agents/skills/video-to-slides/scripts/process.py \
  "runs/.../视频.mp4" \
  --transcript "runs/.../transcript_merged.json" \
  --run-dir "runs/..." \
  --capture-mode audit --video-type auto \
  --force-rebuild slides --force-rebuild align

# 端到端 keep_all=True
... --keep-all-candidates ...
```
