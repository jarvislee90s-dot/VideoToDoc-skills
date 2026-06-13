# Video-to-Slides Skill

> 视频截图去重 → 图文对齐 → 语义整理 → 目录 → 思维导图 → Word

## 功能

- 🖼️ **PPT 截图** - 场景切换 + 15秒兜底，三段式去重
- ⏱️ **图文对齐** - 毫秒级时间轴匹配截图与转录
- 📋 **全文目录** - Agent 自动识别章节并标注时间
- ✨ **语义整理** - Agent 将口语化讲稿改写为书面表达
- 🧠 **思维导图** - Mermaid 格式 + PNG 渲染
- 📄 **多格式输出** - 3 份 Markdown + 2 份 Word

## 工作流程

```
输入视频文件
     │
     ▼
┌───────────────────┐
│   前置检查        │
│ 视频/音频/字幕   │
└─────────┬─────────┘
          │
          ▼
    缺少前置产物？
     /          \
   是            否
   /              \
  ▼               ▼
提示运行      截图 + 去重
video-summary   │
          ┌─────┴─────┐
          │ 三段式去重 │
          │ 场景切换   │
          │ 15秒兜底   │
          └─────┬─────┘
                │
                ▼
          图文对齐
        毫秒级时间轴
                │
                ▼
          ┌─────────────┐
          │ 生成讲义    │
          │ <标题>_讲义 │
          └──────┬──────┘
                 │
                 ▼
        ┌────────────────┐
        │  Agent 目录    │
        │  Agent 语义整理 │
        │  Agent 思维导图 │
        └───────┬────────┘
                │
                ▼
          ┌─────────────┐
          │ <标题>_讲义_整理版 │
          │ <标题>_思维导图    │
          └──────┬──────┘
                 │
                 ▼
            Word 输出
         <标题>_讲义.docx
      <标题>_讲义_整理版.docx
```

## 前置依赖

- **ffmpeg**：截图和音频提取
- **python3** + VideoToDoc 项目 `.venv`
- **mlx-whisper**：ASR 后端（若 transcript.json 需要重新生成）
- **RapidOCR**：截图 OCR 去重
- **mmdc**（mermaid-cli）：思维导图渲染

## 产物

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

## 快速开始

```bash
# 标准流程（需要已有视频和转录）
python3 scripts/process.py "/path/to/video.mp4"

# 缺少转录？先运行 video-summary
python3 ../video-summary/scripts/process.py "视频URL"
```

## 文件结构

```
video-to-slides/
├── SKILL.md               # Skill 操作手册（触发条件、工作流、参数）
├── README.md              # 本文件（项目介绍、安装、产物）
├── scripts/
│   ├── process.py         # 主处理脚本
│   ├── render_mindmap.py  # 思维导图渲染
│   └── _project.py        # 项目路径定位
└── assets/
    └── task_flow.png      # 整体流程图
```

## 与其他 Skill 配合

- **前置**：video-summary（获取视频 + 音频 + 字幕）
- **后续**：feishu-markdown-publish（发布到飞书）

## License

MIT
