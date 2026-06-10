# VideoToDoc

VideoToDoc 是一个面向课程、讲座、培训视频的本地工作流：提取音频、用 Apple Silicon 友好的 `mlx-whisper` 转录文字，自动截取 PPT/讲义页面，把截图和讲稿对齐，生成 Word、Markdown、Mermaid 思维导图，并可发布到飞书文档。

项目同时提供 Codex Skill 源文件，让 Agent 可以通过自然语言触发完整流程。

## 当前状态

截至 2026-05-19，截图/OCR 去重流程已经在示例视频上验证通过；真实 ASR、飞书真实发布、Skill 全局安装尚未完成。

已验证截图结果：

```text
候选图：77 张
最终截图：10 张
OCR 检查：4 组
OCR 判定重复：1 组
OCR 判定保留：3 组
```

当前最终截图目录：

```text
runs/01_第一讲_期权实盘应该避开的_七大误区_08258178726c/selected_slides_audit_0.02_8_15_False
```

注意：当前用 `--asr mock` 跑通的是流程验证，讲稿不是真实转录。下一步需要安装并验证 `mlx-whisper`。

## 功能

- 视频音频提取：基于 `ffmpeg`。
- 本地 ASR：默认 `mlx-whisper`，适配 Apple 芯片。
- 截图检测：支持 `fast`、`fine`、`audit` 三种模式。
- OCR 辅助去重：安装本地 OCR 后，可用文字相似度判断重复页。
- 候选截图审计：生成 `slide_candidates.html`，方便检查是否漏页。
- 图文对齐：按毫秒级时间轴将截图页和转录片段匹配。
- 文档输出：生成 `draft.md`、`draft_compact.md`、`draft_semantic.md`、`draft.docx`、`draft_semantic.docx`、`mindmap.mmd`、`mindmap.png`。
- 质量报告：生成 `quality_report.md`，提示 mock ASR、截图过少、空匹配等风险。
- 飞书发布：通过本机 `lark-cli` 登录态创建文档并显式插入图片。
- Skill 工作流：`skills/videotodoc/` 提供可安装到 Codex 的 Skill。

## 目录结构

```text
VideoToDoc/
├── src/videotodoc/
│   ├── cli.py          # 命令行入口
│   ├── pipeline.py     # 端到端流程编排
│   ├── audio.py        # ffmpeg/ffprobe 音频与时长处理
│   ├── asr.py          # mlx-whisper、faster-whisper、mock ASR 适配
│   ├── slides.py       # 场景检测、兜底抽帧、三段式去重、候选审计
│   ├── ocr.py          # RapidOCR / Tesseract OCR 适配
│   ├── align.py        # 截图页与转录片段时间轴对齐
│   ├── document.py     # Markdown、docx、Mermaid 生成
│   ├── feishu.py       # lark-cli 飞书文档创建与图片插入
│   ├── quality.py      # 质量报告
│   ├── config.py       # 配置、提示词、.env 加载
│   └── models.py       # 统一数据模型
├── skills/videotodoc/
│   ├── SKILL.md
│   └── scripts/process_video.py
├── tests/              # 标准库 unittest 测试
├── Videos/             # 示例视频
├── runs/               # 运行产物，默认不进版本管理
├── config.example.yaml
└── pyproject.toml
```

## 安装

推荐使用项目虚拟环境：

```bash
cd /Users/jarvis/Documents/VideoToDoc
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

安装 OCR：

```bash
.venv/bin/python -m pip install rapidocr onnxruntime
```

安装 Apple Silicon ASR：

```bash
.venv/bin/python -m pip install mlx-whisper
```

飞书发布需要本机已有 `lark-cli`，并完成登录：

```bash
lark-cli config init
lark-cli auth login --recommend
```

## 快速运行

当前已验证的截图/OCR 去重流程：

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

真实 ASR，待安装 `mlx-whisper` 后执行：

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

发布到飞书：

```bash
PYTHONPATH=src .venv/bin/python -m videotodoc.cli publish runs/<run_dir> --target feishu
```

先检查飞书命令，不触碰登录态：

```bash
PYTHONPATH=src .venv/bin/python -m videotodoc.cli publish runs/<run_dir> --target feishu --dry-run
```

## Skill 用法

Skill 源文件位于：

```text
skills/videotodoc/
```

全局安装目标是：

```text
/Users/jarvis/.codex/skills/videotodoc
```

安装后可以自然语言触发，例如：

```text
把这个视频做成讲义，并发布到飞书。
```

Skill 默认会调用：

```bash
python3 /Users/jarvis/Documents/VideoToDoc/skills/videotodoc/scripts/process_video.py \
  "/path/to/video.mp4" \
  --asr mlx-whisper \
  --capture-mode audit \
  --fallback-interval-sec 15 \
  --ocr-dedupe
```

## 截图模式

- `fast`：只使用场景切换，速度快，但容易漏掉渐变式翻页。
- `fine`：场景切换 + 固定间隔兜底抽帧，适合常规课程。
- `audit`：在 `fine` 基础上生成候选截图和 HTML 审计页，适合正式产出。

当前推荐正式截图参数：

```bash
--capture-mode audit
--scene-threshold 0.02
--fallback-interval-sec 15
--hash-threshold 8
--ocr-dedupe
```

常用调参：

```bash
--scene-threshold 0.04
--fallback-interval-sec 15
--hash-threshold 8
--ocr-dedupe
```

如果最终只截出 3 页左右，通常说明阈值太保守或去重过强。请先打开 `slide_candidates.html` 检查候选帧。

如果 PPT 有手写标注或轻微动画，建议启用 OCR 辅助去重：系统会先用图像规则筛出“疑似重复”的相邻页，只有疑似重复才调用 OCR；OCR 文字高度相似且画面变化很小时才合并。未安装 OCR 时会自动降级为图像规则。

三段式相邻页去重规则：

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

## 输出产物

每次运行会生成：

```text
runs/<video_slug>_<hash>/
├── cache/
│   ├── *.wav
│   ├── *.transcript.json
│   ├── *.slides.json
│   └── *.sections.json
├── slides/
│   └── 0001.png ...
├── selected_slides_*/
│   └── 0001.png ...
├── slide_candidates/
│   └── candidate_*.png
├── slide_candidates.html
├── draft.md              # 原始 ASR 换行结构
├── draft_compact.md      # 内容不变、段落更紧凑
├── draft_semantic.md     # Agent 书面整理版
├── draft.docx            # 由 draft_compact.md 生成
├── draft_semantic.docx   # 由 draft_semantic.md 生成
├── mindmap.mmd           # 可手工编辑的 Mermaid 源文件
├── mindmap.png           # 插入两份 Word 的导图图片
└── quality_report.md
```

## 思维导图重渲染

如果手工修改了 `runs/<run_dir>/mindmap.mmd`，运行：

```bash
PYTHONPATH=src .venv/bin/python -m videotodoc.cli render-mindmap runs/<run_dir>
```

也可以直接运行项目脚本：

```bash
python3 scripts/render_mindmap.py runs/<run_dir>
```

它会重新生成 `mindmap.png`，并同时刷新 `draft.docx` 和 `draft_semantic.docx`。优先使用 `mmdc`；如果当前环境不能启动 Chrome，会用 Python/Pillow fallback 生成可插入 Word 的导图图片。

## 配置

复制配置文件：

```bash
cp config.example.yaml config.yaml
```

默认配置要点：

```yaml
asr_backend: mlx-whisper
asr_model: mlx-community/whisper-large-v3-turbo
capture_mode: fine
scene_threshold: 0.02
fallback_interval_sec: 15
ocr_dedupe: true
ocr_similarity_threshold: 0.92
duplicate_change_threshold: 0.005
different_change_threshold: 0.12
different_hash_threshold: 16
mindmap_backend: agent
```

敏感信息不要写入代码或 Skill。当前默认流程不需要 API key；飞书使用 `lark-cli` 登录态。

## 已完成与待办

已完成：

- 项目 CLI 与模块结构。
- RapidOCR 安装、模型下载与 OCR 接入。
- 15 秒候选截图 + scene change。
- 三段式图像/OCR 去重。
- 示例视频最终截图 10 张的验证。
- Markdown、docx、Mermaid、本地质量报告生成。
- 飞书 dry-run 命令拼装。

待办：

- 安装并验证 `mlx-whisper`。
- 运行真实 ASR，替换 `mock` 转录。
- 用真实讲稿验证图文对齐质量。
- 必要时用 `--sync-offset-ms` 校准时间轴。
- 登录并真实发布飞书文档。
- 将 `skills/videotodoc` 安装到 `/Users/jarvis/.codex/skills/videotodoc`。

## 测试

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m compileall src skills/videotodoc/scripts
```

## 故障排查

- `未安装 mlx-whisper`：执行 `.venv/bin/python -m pip install mlx-whisper`。
- OCR 不生效：确认 `.venv/bin/python -c "from rapidocr import RapidOCR"` 可运行。
- `找不到 ffmpeg`：先安装 ffmpeg，并确认 `which ffmpeg` 有输出。
- 飞书 keychain 报错：执行 `lark-cli config init` 和 `lark-cli auth login --recommend`。
- 截图太少：使用 `--capture-mode audit --scene-threshold 0.04 --fallback-interval-sec 10`。
- 文字是假的：检查 `quality_report.md`，如果 ASR 后端是 `mock`，说明没有跑真实转录。

## 安全约定

- 不在聊天、代码或 Skill 正文里保存 API key。
- 不批量删除文件或目录。
- 运行产物默认留在 `runs/`，便于复查和恢复。
