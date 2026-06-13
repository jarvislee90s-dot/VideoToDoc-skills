---
name: video-to-slides
description: "在已有视频、音频、字幕的前提下，自动截图去重、图文对齐、语义整理、生成目录与思维导图、输出 Word/Markdown。触发条件：用户要求把视频整理成带截图的图文讲义；用户要求生成 Word/Markdown 讲义；用户说'做讲义'、'生成课件'、'视频转 PPT 笔记'。"
---

# video-to-slides

视频截图 → 图文讲义。本 Skill 假设已有视频文件和转录文本；如果缺少则提示用户先运行 `video-summary`。

## 工作流

```
① 前置检查
 │
 ├─ 缺视频/音频/字幕 → 提示用户运行 video-summary
 │
 └─ 前置齐全
     │
     ├─② 截图 + 三段式去重（图像规则 + OCR）
     ├─③ 图文对齐（毫秒级时间轴）
     ├─④ 生成 <视频标题>_讲义_<时间戳>.md
     ├─⑤ Agent 全文目录
     ├─⑥ Agent 语义整理 → <视频标题>_讲义_整理版_<时间戳>.md
     ├─⑦ Agent 重写 <视频标题>_思维导图_<时间戳>.mmd
     ├─⑧ 渲染导图 + 刷新 Word
     └─⑨ 输出产物清单
```

### 详细步骤

1. **前置检查**：
   - 确认视频文件、音频文件、`transcript.json` 是否存在。
   - 缺少时提示用户："缺少视频/音频/字幕，请先运行 video-summary Skill"
   - 用户也可提供视频路径，由本 Skill 自动提取音频（但不会获取平台字幕，需要字幕请先运行 video-summary）。

2. **截图 + 去重**：
   - 运行 `scripts/process.py`，默认 `--capture-mode audit --fallback-interval-sec 15 --ocr-dedupe`。
   - 三段式去重：明显重复 → 合并；明显不同 → 保留；不确定 → OCR 判定。
   - 不对全部候选图全量 OCR。

3. **图文对齐**：按毫秒级时间轴将截图页与转录片段匹配。

4. **生成 Markdown**：
   - `<视频标题>_讲义_<时间戳>.md`：保留 ASR 原始换行。
   - `<视频标题>_讲义_紧凑版_<时间戳>.md`：内容不变，只调整段落密度。

5. **全文目录**（Agent）：
   - 阅读 `<视频标题>_讲义_紧凑版_<时间戳>.md` 全文，识别章节划分。
   - 目录写在 `## 图文讲义` 标题之后、`### 第 1 页` 之前。
   - 格式：`- **第一章 章节名称**（00:00 - 05:30）：简短概述`
   - 章节划分依据语义转折，不是按页数均分。

6. **语义整理**（Agent）：
   - 把 `<视频标题>_讲义_整理版_<时间戳>.md` 改写成书面整理版。
   - 保留每页图片、页码、时间。
   - 不新增视频里没有的事实，去掉口播冗余。

7. **思维导图**（Agent）：
   - 基于书面整理版重写 `<视频标题>_思维导图_<时间戳>.mmd`。

8. **渲染 + 刷新 Word**：
   - 运行 `scripts/render_mindmap.py` 渲染导图为 PNG。
   - 重新生成 `<视频标题>_讲义_<时间戳>.docx` 与 `<视频标题>_讲义_整理版_<时间戳>.docx`。

9. **输出**：run 目录、三份 Markdown、两份 Word、思维导图、质量报告。

## 默认命令

```bash
# 标准流程（需要已有视频和转录）
python3 skills/video-to-slides/scripts/process.py "/path/to/video.mp4"

# 指定已有转录
python3 skills/video-to-slides/scripts/process.py "/path/to/video.mp4" \
  --transcript runs/<视频标题>_<时间戳>/transcript.json

# 快速测试
python3 skills/video-to-slides/scripts/process.py "/path/to/video.mp4" --asr mock

# 手工修改思维导图后刷新
python3 skills/video-to-slides/scripts/render_mindmap.py runs/<视频标题>_<时间戳>
```

## 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `video` | （必填） | 视频文件路径 |
| `--project-dir` | 自动检测 | VideoToDoc 项目根目录 |
| `--asr` | `mlx-whisper` | ASR 后端 |
| `--transcript` | `None` | 已有转录文件路径（跳过 ASR） |
| `--capture-mode` | `audit` | 截图模式：fast/fine/audit |
| `--fallback-interval-sec` | `15` | 兜底截图间隔秒数 |
| `--ocr-dedupe` | 开启 | 启用 OCR 辅助去重 |
| `--sync-offset-ms` | `None` | 时间偏移修正（毫秒） |
| `--force-rebuild` | `[]` | 重跑步骤：audio/asr/slides/align |

## 截图去重规则

1. **明显重复**：`change_ratio < 0.005` 且 `dHash <= 8` → 合并，保留后一张
2. **明显不同**：`change_ratio >= 0.12` 或 `dHash > 16` → 保留新页
3. **不确定**：调用 OCR；文本相似度 `>= 0.92` 且变化面积 `< 0.12` → 重复，否则保留

不要对全部候选图全量 OCR。白底 PPT 容易误合并，建议开启 `--ocr-dedupe`。

## Word 样式规范

- **文章标题**：黑色大标题，居中
- **页码行**：蓝色页码 + 灰色时间
- **正文**：10.5-11pt，1.15 倍行距，段前 0，段后 0.5 行
- **分隔线**：每页之间水平分隔线
- **思维导图**：文档末尾

## 产物结构

```
runs/<视频标题>_<时间戳>/
├── <视频标题>_讲义_<时间戳>.md              # 原始换行版
├── <视频标题>_讲义_紧凑版_<时间戳>.md       # 紧凑段落版
├── <视频标题>_讲义_整理版_<时间戳>.md       # 书面整理版
├── <视频标题>_讲义_<时间戳>.docx           # 原文 Word
├── <视频标题>_讲义_整理版_<时间戳>.docx     # 整理版 Word
├── <视频标题>_思维导图_<时间戳>.mmd         # Mermaid 导图源文件
├── <视频标题>_思维导图_<时间戳>.png         # 渲染后的导图
├── <视频标题>_质量报告_<时间戳>.md          # 质量报告
└── selected_slides_<模式>_<参数>/          # 最终截图
```

## 与其他 Skill 的关系

- **video-summary**：前置 Skill。缺少视频/音频/字幕时，引导用户先运行它。
- **feishu-markdown-publish**：后续 Skill。生成 Word 后，如需发布飞书使用它。

## 注意事项

1. 不要默认用 5 秒截图间隔，默认 15 秒
2. 不要只用 dHash 判断白底 PPT，容易误合并
3. 不要把 key 写进 Skill；飞书依赖本机 lark-cli
4. 不批量删除文件或目录；产物保留在 `runs/` 下
5. 使用 `mock` ASR 时必须告知用户讲稿非真实转录
