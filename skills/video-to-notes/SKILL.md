---
name: video-to-notes
description: "输入网页视频链接，自动下载视频、提取音频、ASR 转文字，然后由 Agent 总结生成 Markdown 讲稿。"
---

# video-to-notes

将网页视频一键转为结构化 Markdown 笔记。

## 触发条件

- 用户提供视频链接并要求转文字、总结、做笔记
- 用户说"把这个视频整理成笔记"、"帮我总结这个视频"等
- 用户提到"视频转文字"、"视频摘要"、"video to notes"

## 前置依赖

脚本启动时会自动检查，缺少依赖会提示安装命令：

- **yt-dlp**：`pip install yt-dlp pycryptodomex`
- **ffmpeg**：`brew install ffmpeg`（macOS）
- **mlx-whisper**：`pip install mlx-whisper`

## 使用流程

### 1. 运行 process.py

```bash
python3 /Users/jarvis/Documents/VideoToDoc/skills/video-to-notes/scripts/process.py "<视频URL>"
```

常用参数：

```bash
python3 scripts/process.py "<URL>" \
  --resolution 720p \
  --language zh \
  --asr-model mlx-community/whisper-large-v3-turbo \
  --cleanup all
```

### 2. 读取转录文本

脚本输出 JSON，其中 `transcript_txt` 是纯文本转录的路径。读取该文件。

### 3. Agent 总结

读取 `transcript_txt` 内容后，**用你自身的 LLM 能力**对转录文本进行总结和提炼，生成结构化的 Markdown 讲稿。总结要求：

- 提取核心观点和关键信息
- 按主题分段，使用二级/三级标题
- 保留重要细节（数字、专有名词、关键论据）
- 用列表和引用块突出要点
- 语言与原视频一致

### 4. 写入 summary.md

将总结写入 `<run_dir>/summary.md`。

## 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `url` | （必填） | 视频网页链接 |
| `--output-dir` | `./runs` | 产物输出目录 |
| `--resolution` | `best` | 视频分辨率：best/2160p/1080p/720p/480p/360p/audio |
| `--asr-model` | `mlx-community/whisper-large-v3-turbo` | mlx-whisper 模型 |
| `--language` | `zh` | ASR 语言 |
| `--proxy` | 自动检测 | 代理地址（部分站点自动匹配） |
| `--cleanup` | 不清理 | `all`=删视频+音频；`transcript-only`=只保留 summary.md |

## 产物结构

```
runs/<标题>_<hash>/
├── video.mp4             # 下载的视频
├── audio.wav             # 提取的音频
├── transcript.json       # ASR 结果（带时间戳）
├── transcript.txt        # 纯文本转录
└── summary.md            # Agent 总结（你写入）
```

## 注意事项

- ASR 使用本地 mlx-whisper，需要 Apple Silicon Mac
- 大型视频转录可能需要数分钟，请耐心等待
- 如果视频平台有自带字幕，可考虑先尝试 yt-dlp 的字幕提取（当前版本未实现，未来可扩展）
- `--resolution audio` 可只下载音频轨道，节省时间和空间（如果不需要视频画面）
- 脚本有缓存机制：已下载的视频和已转录的结果会跳过，除非手动删除
