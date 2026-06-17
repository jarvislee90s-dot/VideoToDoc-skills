# VideoToDoc Skills

> 视频 → 讲义 → 飞书文档的完整工作流

三个协同工作的 Skill，实现从视频到飞书文档的自动化转换。

## 整体流程

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         VideoToDoc 完整工作流                             │
└─────────────────────────────────────────────────────────────────────────┘

  视频 URL / 本地文件
        │
        ▼
┌─────────────────────────────────┐
│      video-summary               │
│  ┌─────────────────────────────┐  │
│  │ 1. 获取字幕（优先）          │  │
│  │    有字幕 → 直接保存        │  │
│  │    无字幕 → 下载视频        │  │
│  │ 2. 提取音频 → ASR 转录      │  │
│  │ 3. 生成 transcript          │  │
│  │ 4. Agent 生成摘要           │  │
│  └─────────────────────────────┘  │
└─────────────┬─────────────────────┘
              │
              ▼
        runs/<视频标题>_<时间戳>/
        ├── video.mp4（如需ASR）
        ├── transcript.json
        ├── transcript.txt
        └── <视频标题>_总结_<时间戳>.md
              │
              ▼
┌─────────────────────────────────┐
│      video-to-slides             │
│  ┌─────────────────────────────┐  │
│  │ 1. 截图 + 三段式去重        │  │
│  │ 2. 图文对齐（时间轴）        │  │
│  │ 3. 生成讲义 Markdown        │  │
│  │ 4. Agent 全文目录           │  │
│  │ 5. Agent 语义整理           │  │
│  │ 6. Agent 思维导图           │  │
│  │ 7. 渲染导图 + Word 输出     │  │
│  └─────────────────────────────┘  │
└─────────────┬─────────────────────┘
              │
              ▼
        runs/<视频标题>_<时间戳>/
        ├── <视频标题>_讲义_<时间戳>.md
        ├── <视频标题>_讲义_整理版_<时间戳>.md
        ├── <视频标题>_讲义_<时间戳>.docx
        ├── <视频标题>_讲义_整理版_<时间戳>.docx
        ├── <视频标题>_思维导图_<时间戳>.mmd
        └── <视频标题>_思维导图_<时间戳>.png
              │
              ▼
┌─────────────────────────────────┐
│   feishu-markdown-publish        │
│  ┌─────────────────────────────┐  │
│  │ 1. 解析 Markdown 结构       │  │
│  │ 2. 创建飞书文档             │  │
│  │ 3. 逐页发布（标题/图片/正文）│  │
│  │ 4. 追加思维导图             │  │
│  │ 5. 返回飞书文档 URL         │  │
│  └─────────────────────────────┘  │
└─────────────────────────────────┘
              │
              ▼
        飞书云文档
```

## Skill 说明

### 1. video-summary

**功能**：视频 URL 或本地文件 → 字幕优先获取 → 无字幕时 ASR → 生成摘要

**核心设计**：字幕优先，ASR fallback。有字幕时直接保存为 transcript，跳过视频下载和 ASR。

**输入**：视频 URL 或本地文件路径
**输出**：
- `runs/<视频标题>_<时间戳>/`
  - `transcript.json` + `transcript.txt`
  - `<视频标题>_总结_<时间戳>.md`
  - `video.mp4`（如需 ASR）

[查看详细说明 →](video-summary/README.md)
[查看操作手册 →](video-summary/SKILL.md)

### 2. video-to-slides

**功能**：视频截图去重 → 图文对齐 → 语义整理 → 目录 → 思维导图 → Word

**输入**：video.mp4 + transcript.json（来自 video-summary）
**输出**：
- `runs/<视频标题>_<时间戳>/`
  - `<视频标题>_讲义_<时间戳>.md`
  - `<视频标题>_讲义_整理版_<时间戳>.md`
  - `<视频标题>_讲义_<时间戳>.docx`
  - `<视频标题>_讲义_整理版_<时间戳>.docx`
  - `<视频标题>_思维导图_<时间戳>.mmd`
  - `<视频标题>_思维导图_<时间戳>.png`

[查看详细说明 →](video-to-slides/README.md)
[查看操作手册 →](video-to-slides/SKILL.md)

### 3. feishu-markdown-publish

**功能**：Markdown 文档 → 飞书云文档

**输入**：`<视频标题>_讲义_整理版_<时间戳>.md`（来自 video-to-slides）
**输出**：飞书云文档 URL

[查看详细说明 →](feishu-markdown-publish/README.md)
[查看操作手册 →](feishu-markdown-publish/SKILL.md)

## 快速开始

### 安装依赖

```bash
# 1. 克隆仓库
git clone <repository-url>
cd VideoToDoc/skills

# 2. 安装 Python 依赖
pip install -r requirements.txt

# 3. 安装系统依赖（macOS）
brew install ffmpeg

# 4. 安装 lark-cli（发布到飞书需要）
npm install -g @lark-cli/cli
lark-cli config init
lark-cli auth login --recommend
```

### 完整工作流

```bash
# Step 1: 视频 → 摘要（字幕优先）
cd video-summary
python3 scripts/process.py "https://www.youtube.com/watch?v=xxx"
# 输出：runs/<视频标题>_<时间戳>/<视频标题>_总结_<时间戳>.md
cd ..

# Step 2: 视频 → 讲义
cd video-to-slides
python3 scripts/process.py "runs/<视频标题>_<时间戳>/video.mp4"
# 输出：runs/<视频标题>_<时间戳>/<视频标题>_讲义_整理版_<时间戳>.md
cd ..

# Step 3: 讲义 → 飞书
cd feishu-markdown-publish
python3 scripts/publish.py \
  "../video-to-slides/runs/<视频标题>_<时间戳>/<视频标题>_讲义_整理版_<时间戳>.md" \
  "https://example.feishu.cn/wiki/space/<space_id>"
```

## 目录结构

```
skills/
├── README.md                          # 本文件（项目总览）
├── requirements.txt                   # Python 依赖
├── video-summary/                     # Skill 1: 视频摘要
│   ├── README.md                      # 项目介绍、安装、产物
│   ├── SKILL.md                       # 操作手册（触发条件、工作流、参数）
│   ├── scripts/
│   │   ├── process.py
│   │   └── _project.py
│   └── assets/
│       └── task_flow.png
├── video-to-slides/                   # Skill 2: 图文讲义
│   ├── README.md                      # 项目介绍、安装、产物
│   ├── SKILL.md                       # 操作手册（触发条件、工作流、参数）
│   ├── scripts/
│   │   ├── process.py
│   │   ├── render_mindmap.py
│   │   └── _project.py
│   └── assets/
│       └── task_flow.png
└── feishu-markdown-publish/           # Skill 3: 飞书发布
    ├── README.md                      # 项目介绍、安装、产物
    ├── SKILL.md                       # 操作手册（触发条件、工作流、参数）
    ├── scripts/
    │   ├── publish.py
    │   └── _project.py
    └── assets/
        └── task_flow.png
```

## 依赖说明

### Python 依赖

```
yt-dlp>=2024.1.0
pycryptodomex
mlx-whisper
curl_cffi
python-docx
rapidocr
```

### 系统依赖

- **Python 3.10+**
- **ffmpeg** - 视频/音频处理
- **Node.js** - lark-cli 运行环境
- **lark-cli** - 飞书文档发布

## 环境要求

- **操作系统**：macOS（推荐，Apple Silicon 优化）/ Linux
- **Python**：3.10+
- **硬件**：建议 16GB+ 内存（mlx-whisper ASR 需要）

## 贡献指南

1. Fork 本仓库
2. 创建功能分支：`git checkout -b feature/xxx`
3. 提交更改：`git commit -am 'Add some feature'`
4. 推送分支：`git push origin feature/xxx`
5. 提交 Pull Request

## 许可证

MIT License
