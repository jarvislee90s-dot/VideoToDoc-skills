# Video-Summary Skill

> 视频 URL 或本地文件 → 字幕优先获取 → 无字幕时 ASR 转录 → 生成摘要

## 功能

- 🌐 **URL 下载** - yt-dlp 下载 YouTube/B站等平台视频
- 🔤 **字幕优先** - 优先获取平台原生字幕（秒级），有字幕时**跳过视频下载、音频提取、ASR**
- 🎵 **音频提取** - ffmpeg 提取音频（仅 ASR 时需要）
- 🎙️ **ASR 转录** - mlx-whisper（Apple Silicon 优化）语音转文字
- 📝 **Agent 摘要** - 自动生成结构化 Markdown 摘要

## 工作流程

```
输入视频 URL 或本地文件
        │
        ▼
┌───────────────────┐
│   依赖检查        │
│ ffmpeg / yt-dlp   │
│ mlx-whisper       │
└─────────┬─────────┘
          │
          ▼
    是 URL？
     /    \
   是      否
   /        \
  ▼          ▼
┌─────────────────┐    ┌─────────────────┐
│  URL 输入流程    │    │ 本地文件流程     │
│                 │    │                 │
│ ① 获取平台字幕  │    │ ① 提取音频      │
│    (字幕优先策略)│    │ ② ASR 转录      │
└────────┬────────┘    └─────────────────┘
         │
         ▼
    有字幕？
     /    \
   是      否
   /        \
  ▼          ▼
┌──────────────┐    ┌──────────────┐
│ 字幕成功     │    │ 无字幕       │
│              │    │              │
│ 直接保存为   │    │ 下载视频     │
│ transcript   │    │ 提取音频     │
│ (跳过 ASR)   │    │ ASR 转录     │
└──────┬───────┘    └──────┬───────┘
       │                   │
       └─────────┬─────────┘
                 │
                 ▼
         ┌─────────────┐
         │ transcript  │
         │ .json/.txt  │
         └──────┬──────┘
                │
                ▼
         Agent 生成摘要
                │
                ▼
    <视频标题>_总结_<时间戳>.md
```

## 字幕优先策略

本 Skill 的核心设计：**字幕优先，ASR fallback**。

当输入为 URL 时：
1. **优先获取平台原生字幕**（YouTube/B站等的人工字幕或自动字幕）
2. **字幕语言优先级**：`zh-Hans > zh > en > 其他`
3. **字幕成功** → 直接解析保存为 `transcript.json` + `transcript.txt`，**跳过视频下载、音频提取、ASR 转录**
4. **无字幕** → 下载视频 → 提取音频 → ASR 转录

当输入为本地文件时：
- 直接提取音频 → ASR 转录（本地文件无法获取平台字幕）

## 快速开始

```bash
# URL 输入（会自动尝试获取字幕）
python3 scripts/process.py "https://www.youtube.com/watch?v=xxx"

# 本地视频（直接走 ASR）
python3 scripts/process.py "/path/to/video.mp4"

# 强制跳过字幕，使用 ASR
python3 scripts/process.py "https://www.youtube.com/watch?v=xxx" --no-subtitle

# 诊断依赖
python3 scripts/process.py doctor
```

## 前置依赖

运行 `python3 scripts/process.py doctor` 检查：

- **yt-dlp**：`pip install yt-dlp pycryptodomex`（URL 输入时必需）
- **ffmpeg**：`brew install ffmpeg`（macOS）/ `apt install ffmpeg`（Linux）
- **mlx-whisper**：`pip install mlx-whisper`（ASR 时需要，字幕成功则可跳过）
- **curl_cffi**：`pip install curl_cffi`（可选，B站 TLS 指纹绕过）

## 产物

```
runs/<视频标题>_<时间戳>/
├── video.mp4                              # 下载的视频（URL 输入且需要 ASR 时）
├── audio.wav                              # 提取的音频（需要 ASR 时）
├── transcript.json                        # 带时间戳的转录（字幕或 ASR）
├── transcript.txt                         # 纯文本转录
└── <视频标题>_总结_<时间戳>.md            # Agent 生成的摘要
```

**注意**：如果成功获取字幕，`video.mp4` 和 `audio.wav` **不会生成**。

## 文件结构

```
video-summary/
├── SKILL.md          # Skill 操作手册（触发条件、工作流、参数）
├── README.md         # 本文件（项目介绍、安装、产物）
├── scripts/
│   ├── process.py    # 主处理脚本
│   └── _project.py   # 项目路径定位
└── assets/
    └── task_flow.png # 整体流程图
```

## 与 video-to-slides 配合

本 Skill 的产物（video + audio + transcript）可直接作为 video-to-slides 的输入。

**特别说明**：video-to-slides 需要 `video.mp4` 作为输入。如果 video-summary 通过字幕直接输出了 transcript（没有下载视频），你需要：
1. 确保原视频文件可访问
2. 或者重新运行 video-summary 加上 `--no-subtitle` 强制下载视频

## License

MIT
