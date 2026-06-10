# video-to-notes Skill 设计文档

> 日期：2026-06-10
> 状态：已批准

## 概述

一个独立的 Codex Skill，输入网页视频链接，自动完成：下载视频 → 提取音频 → ASR 转文字 → Agent 总结生成 Markdown。

## 核心流程

```
网页 URL
  │
  ▼
① yt-dlp 下载视频 → video.mp4
  │
  ▼
② ffmpeg 提取音频 → audio.wav
  │
  ▼
③ mlx-whisper 转录 → transcript.json + transcript.txt
  │
  ▼
④ 输出 transcript.txt，让 Agent 自行总结 → summary.md
```

步骤 ①②③ 由 `process.py` 脚本完成；步骤 ④ 由 SKILL.md 指导 Agent 用自身 LLM 能力完成。

## 目录结构

```
~/.codex/skills/video-to-notes/
├── SKILL.md              # Skill 描述、触发规则、参数说明
└── scripts/
    └── process.py        # 主流程脚本（步骤 ①②③ + 产物管理）
```

## 产物目录

每次运行生成：

```
runs/<video_slug>_<hash>/
├── video.mp4             # 下载的视频
├── audio.wav             # 提取的音频
├── transcript.json       # ASR 结果（带时间戳、置信度）
├── transcript.txt        # 纯文本转录（方便 Agent 阅读）
└── summary.md            # Agent 总结（由 Agent 写入）
```

### 清理选项

- `--cleanup all`：删除视频和音频文件，保留转录和总结
- `--cleanup transcript-only`：只保留 summary.md
- 不传 `--cleanup`：保留所有产物（默认）

## process.py 接口

```bash
python3 scripts/process.py <url> \
  [--output-dir ./runs] \
  [--resolution best] \
  [--asr-model mlx-community/whisper-large-v3-turbo] \
  [--proxy http://...] \
  [--cleanup all|transcript-only] \
  [--language zh]
```

### 依赖检查

脚本启动时一次性检查：
- `yt-dlp`：未安装提示 `pip install yt-dlp pycryptodomex`
- `ffmpeg`：未安装提示 `brew install ffmpeg`
- `mlx_whisper`：未安装提示 `pip install mlx-whisper`

缺任一依赖打印安装命令并以非零退出码退出。

### 输出格式

脚本成功后打印 JSON 到 stdout：

```json
{
  "run_dir": "/path/to/runs/<slug>_<hash>",
  "video": "/path/to/runs/<slug>_<hash>/video.mp4",
  "audio": "/path/to/runs/<slug>_<hash>/audio.wav",
  "transcript_json": "/path/to/runs/<slug>_<hash>/transcript.json",
  "transcript_txt": "/path/to/runs/<slug>_<hash>/transcript.txt"
}
```

Agent 读取 `transcript_txt` 做总结，写入 `summary.md`。

## 关键决策

| 决策 | 选择 | 理由 |
|------|------|------|
| ASR 后端 | mlx-whisper（本地） | Apple Silicon 优化，零 API 费用 |
| 总结方式 | Agent 自身 LLM | 无需额外 API，最方便 |
| 依赖安装 | 入口一次性检查 | 步骤串行必需，分步检查无意义 |
| 与 VideoToDoc 关系 | 独立实现，参考逻辑 | 避免 OCR/slides 等不需要的依赖 |
| 代理支持 | 参考站点映射逻辑 | 复用 VideoDownloader 的代理策略 |

## 不做的事（YAGNI）

- 不做 PPT 截图 / OCR / 图文对齐
- 不做飞书发布
- 不做 docx 生成
- 不调外部总结 API
- 不封装为 MCP Server

## 未来扩展

- 可在第 5 步加入 PPT 截图 + 图文对齐（参考 VideoToDoc 的 slides.py + align.py）
- 可加入更多 ASR 后端（faster-whisper 等）
