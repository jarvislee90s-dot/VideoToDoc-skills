# VideoToDoc 交接计划 V2

更新时间：2026-05-19  
项目目录：`/Users/jarvis/Documents/VideoToDoc`

## 目标

把课程/讲座视频转成可编辑讲义。最终工作流应由 Codex Skill 触发，用户用自然语言说明视频路径和需求，Agent 自动执行：

```text
视频课程
  -> 检查依赖
  -> 生成完整候选截图序列
  -> 图像/OCR 去重，保留每页最后一张
  -> 提取音频
  -> ASR 转录讲稿
  -> 截图与讲稿按时间轴对齐
  -> 生成 Word / Markdown / Mermaid
  -> 通过 lark-cli 发布到飞书文档
```

## 当前已完成

### 1. 项目骨架与 CLI

已实现 Python 项目结构：

- `src/videotodoc/cli.py`：命令行入口。
- `src/videotodoc/pipeline.py`：端到端流程编排。
- `src/videotodoc/audio.py`：`ffmpeg/ffprobe` 音频与时长处理。
- `src/videotodoc/asr.py`：`mlx-whisper`、`faster-whisper`、`mock` 后端接口。
- `src/videotodoc/slides.py`：截图候选、去重、OCR 辅助判断。
- `src/videotodoc/ocr.py`：RapidOCR 优先，Tesseract fallback。
- `src/videotodoc/align.py`：截图与转录片段时间轴对齐。
- `src/videotodoc/document.py`：Markdown、docx、Mermaid 生成。
- `src/videotodoc/feishu.py`：`lark-cli` 创建飞书文档与插入图片。
- `src/videotodoc/quality.py`：质量报告。

### 2. 截图流程已完成并验证

当前截图策略已经按实际视频调通：

1. 先生成候选截图序列。
2. 默认兜底间隔为 `15` 秒，可通过 `--fallback-interval-sec` 改为 10、20 等。
3. 同时加入 `ffmpeg` scene change 结果，避免只靠固定间隔漏掉快速翻页。
4. 先使用图像规则判断相邻图片是否明显重复或明显不同。
5. 明显重复：直接合并，并保留时间序列上最后一张图。
6. 明显不同：直接保留为新页。
7. 不确定相邻对：调用 RapidOCR，比较 OCR 文本相似度。
8. OCR 文本相似度高于阈值时视为同一页，否则保留为新页。
9. 最终入选页再做精确 seek 抽帧，避免切换点附近跳到下一页。

当前三段式判定规则：

```text
如果 change_ratio < 0.005 且 dHash距离 <= 8：
    明显重复，直接合并，保留后一张

如果 change_ratio >= 0.12 或 dHash距离 > 16：
    明显不同，直接保留

否则：
    进入 OCR
    如果 OCR 文本相似度 >= 0.92 且 change_ratio < 0.12：
        判为重复，保留后一张
    否则：
        判为新页
```

### 3. OCR 已安装并接入

已在项目虚拟环境 `.venv` 中安装：

```bash
.venv/bin/python -m pip install rapidocr onnxruntime
```

RapidOCR 模型已下载成功，当前使用 PP-OCRv4 mobile ONNX 模型：

- `ch_PP-OCRv4_det_mobile.onnx`
- `ch_ppocr_mobile_v2.0_cls_mobile.onnx`
- `ch_PP-OCRv4_rec_mobile.onnx`

已验证候选图 `candidate_0018_320000.png` 能识别出核心文字“买入过于虚值的期权”。

### 4. 示例视频截图验收结果

示例视频：

```text
Videos/01_第一讲 期权实盘应该避开的“七大误区”.mp4
```

已用以下参数跑通截图：

```bash
PYTHONPATH=src .venv/bin/python -m videotodoc.cli process \
  "Videos/01_第一讲 期权实盘应该避开的“七大误区”.mp4" \
  --asr mock \
  --capture-mode audit \
  --scene-threshold 0.02 \
  --fallback-interval-sec 15 \
  --hash-threshold 8 \
  --ocr-dedupe \
  --force-rebuild slides \
  --force-rebuild align
```

结果：

```text
候选图：77 张
最终截图：10 张
OCR 检查：4 组
OCR 判定重复：1 组
OCR 判定保留：3 组
```

质量报告：

```text
runs/01_第一讲_期权实盘应该避开的_七大误区_08258178726c/quality_report.md
```

最终截图目录：

```text
runs/01_第一讲_期权实盘应该避开的_七大误区_08258178726c/selected_slides_audit_0.02_8_15_False
```

人工指出可能漏掉的 `candidate_0018_320000.png` 已保留为最终第 3 页。

### 5. Skill 源文件已创建

Skill 源文件在：

```text
skills/videotodoc/SKILL.md
skills/videotodoc/scripts/process_video.py
```

计划安装位置：

```text
/Users/jarvis/.codex/skills/videotodoc
```

此前写入全局 Skill 目录时权限审批超时，因此目前 Skill 先保存在项目内。后续需要复制到全局目录。

## 当前未完成

### 1. 真实 ASR 尚未完成

当前跑通的是 `--asr mock`，讲稿不是视频真实转录。

计划默认 ASR：

```text
mlx-whisper
```

原因：

- 用户是 Apple 芯片。
- `mlx-whisper` 更适合 Apple Silicon 本地推理。
- 不使用 Ollama 做 ASR 或摘要。

已在代码中加入 `mlx-whisper` 后端，但依赖尚未完成安装/真实转录验证。

待执行：

```bash
.venv/bin/python -m pip install mlx-whisper
```

然后用真实 ASR 跑：

```bash
PYTHONPATH=src .venv/bin/python -m videotodoc.cli process \
  "Videos/01_第一讲 期权实盘应该避开的“七大误区”.mp4" \
  --asr mlx-whisper \
  --capture-mode audit \
  --scene-threshold 0.02 \
  --fallback-interval-sec 15 \
  --hash-threshold 8 \
  --ocr-dedupe \
  --force-rebuild asr \
  --force-rebuild align
```

### 2. 图文对齐仍是基础版本

当前已有按时间轴对齐逻辑：

- 每页截图有 `start_ms/end_ms/capture_ms`。
- ASR 分段有 `start_ms/end_ms/text`。
- 相交时间段内的文字会归到该页下。

但由于真实 ASR 尚未跑通，目前还没有真实讲稿验证。后续需要：

- 检查 ASR 时间戳与视频时间轴是否有 offset。
- 必要时使用 `--sync-offset-ms` 人工修正。
- 处理讲稿跨页、老师提前/滞后讲解的问题。

### 3. 飞书发布尚未真实验证

飞书策略已明确：

1. 先生成本地 `draft.md`。
2. 用 `lark-cli docs +create` 创建飞书文档。
3. 用 `lark-cli docs +media-insert` 显式上传并插入每张图。

当前本机 `lark-cli` 可用，但真实发布依赖用户本机登录：

```bash
lark-cli config init
lark-cli auth login --recommend
```

已实现 dry-run，不触碰 keychain：

```bash
PYTHONPATH=src python3 -m videotodoc.cli publish runs/<run_dir> --target feishu --dry-run
```

真实发布待验证。

### 4. Skill 尚未全局安装

需要将项目内 Skill 复制到：

```text
/Users/jarvis/.codex/skills/videotodoc
```

注意：

- 不要在 Skill 里写 API key。
- 飞书使用本机 `lark-cli` 登录态。
- Agent 智能整理由执行 Skill 的 Agent 完成，不接 Ollama。

## 推荐的下一步执行顺序

1. 安装并验证 `mlx-whisper`。
2. 用当前 10 张截图结果跑真实 ASR。
3. 生成真实 `transcript.json`。
4. 重新生成 `sections.json`、`draft.docx`、`draft.md`、`mindmap.mmd`。
5. 人工抽查图文对齐质量。
6. 登录飞书并 dry-run。
7. 真实发布飞书文档。
8. 将 `skills/videotodoc` 安装到全局 Skill 目录。

## 推荐交接命令

### 检查测试

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m compileall src skills/videotodoc/scripts
```

### 快速复现当前截图结果

```bash
PYTHONPATH=src .venv/bin/python -m videotodoc.cli process \
  "Videos/01_第一讲 期权实盘应该避开的“七大误区”.mp4" \
  --asr mock \
  --capture-mode audit \
  --scene-threshold 0.02 \
  --fallback-interval-sec 15 \
  --hash-threshold 8 \
  --ocr-dedupe \
  --force-rebuild slides \
  --force-rebuild align
```

### Skill 脚本入口

```bash
python3 skills/videotodoc/scripts/process_video.py \
  "Videos/01_第一讲 期权实盘应该避开的“七大误区”.mp4" \
  --asr mock \
  --capture-mode audit \
  --fallback-interval-sec 15 \
  --ocr-dedupe
```

## 注意事项

- 不要再用 5 秒兜底作为默认值，会导致候选过密和 OCR 成本过高。
- 不要对所有候选图全量 OCR；只对三段式判断中的“不确定相邻对”做 OCR。
- 不要只依赖 dHash；白底 PPT 很容易误合并不同页。
- 不要用快速 seek 截最终页；最终入选页需要精确 seek。
- 候选审计图可以快速 seek，因为只用于浏览和粗筛。
- 不要批量删除文件或目录。
