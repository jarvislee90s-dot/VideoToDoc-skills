---
name: video-to-notes
description: "输入网页视频链接，自动获取字幕或 ASR 转文字，由 Agent 总结生成 Markdown 讲稿。"
---

# video-to-notes

将网页视频一键转为结构化 Markdown 笔记。

## 触发条件

- 用户提供视频链接并要求转文字、总结、做笔记
- 用户说"把这个视频整理成笔记"、"帮我总结这个视频"等
- 用户提到"视频转文字"、"视频摘要"、"video to notes"

## 工作流

```
URL
 │
 ├─① 尝试获取平台原生字幕（快，秒级）
 │   ├─ 有字幕 → 直接保存为 transcript.txt
 │   └─ 无字幕 → ② 下载音频 → ③ ASR 转录
 │
 └─④ Agent 读取 transcript.txt → 自行总结 → 写入 summary.md
```

**字幕优先策略**：优先下载平台原生字幕（YouTube/B站等），比 ASR 快很多且无错字。无字幕时才 fallback 到本地 mlx-whisper。

## 前置依赖

运行 `python3 scripts/process.py doctor` 检查：

- **yt-dlp**：`pip install yt-dlp pycryptodomex`
- **ffmpeg**：`brew install ffmpeg`（macOS）
- **mlx-whisper**：`pip install mlx-whisper`（ASR fallback 时需要）
- **curl_cffi**：`pip install curl_cffi`（可选，B站 TLS 指纹绕过）

## 使用方式

### 一条命令跑完

```bash
python3 scripts/process.py "<视频URL>"
```

### 诊断依赖

```bash
python3 scripts/process.py doctor
```

### 常用参数

```bash
python3 scripts/process.py "<URL>" --language zh --cleanup all
python3 scripts/process.py "<URL>" --no-subtitle    # 跳过字幕，强制 ASR
```

### Agent 总结

脚本输出 JSON，其中 `transcript_txt` 是纯文本转录路径。Agent 读取后用自身 LLM 能力总结，写入 `summary.md`。

总结要求：
- 提取核心观点和关键信息
- 按主题分段，使用二级/三级标题
- 保留重要细节（数字、专有名词、关键论据）
- 用列表和引用块突出要点

## 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `url` | （必填） | 视频网页链接 |
| `--output-dir` | `./runs` | 产物输出目录 |
| `--asr-model` | `mlx-community/whisper-large-v3-turbo` | mlx-whisper 模型 |
| `--language` | `zh` | 字幕/ASR 语言 |
| `--proxy` | 根据站点自动匹配，或手动指定 | 代理地址 |
| `--cleanup` | 不清理 | `all`=删音频；`transcript-only`=只保留 summary.md |
| `--no-subtitle` | 关闭 | 跳过字幕，强制使用 ASR |

## 代理配置

通过环境变量 `VIDEO_TO_NOTES_PROXY_MAP` 配置站点专属代理：

```bash
export VIDEO_TO_NOTES_PROXY_MAP="example.com:127.0.0.1:8080;other.site:127.0.0.1:9090"
```

或命令行直接指定：

```bash
python3 scripts/process.py "<URL>" --proxy "http://127.0.0.1:8080"
```

优先级：命令行 `--proxy` > 环境变量站点映射 > 无代理

## 产物结构

```
runs/<标题>_<hash>/
├── transcript.json   # 结构化转录（带时间戳）
├── transcript.txt    # 纯文本转录（Agent 读取）
└── summary.md        # Agent 总结（你写入）
```

## 字幕优先策略

借鉴 AI-Video-Transcriber 的设计：

1. 先用 yt-dlp 探测视频信息（`extract_info(download=False)`）
2. 检查 `subtitles`（人工字幕）和 `automatic_captions`（自动字幕）
3. 优先人工字幕，其次自动字幕
4. 按语言优先级选择：`zh-Hans > zh > en > 其他`
5. 仅下载字幕文件（`skip_download=True`），解析为纯文本
6. 无字幕时 fallback 到 ASR

优势：
- 字幕获取通常 **1-2 秒**，ASR 需要数分钟
- 平台原生字幕通常比 ASR 更准确（人工校对）
- 节省磁盘空间（不需要下载音频文件）

## B站支持

B站视频需要 `buvid3/buvid4` 指纹 cookies 才能下载。脚本会自动从 B站 finger API 获取并注入。

当前 B站 playurl API 有 412 反爬问题，这是 yt-dlp 上游的已知问题（PR #16889）。临时解决方案：
- 安装 `curl_cffi`：`pip install curl_cffi`
- 等 yt-dlp 上游修复后升级：`pip install -U yt-dlp`

## 异常处理

- **脚本中途失败**：已有产物会被缓存跳过，重新运行从断点继续
- **字幕下载失败**：自动 fallback 到 ASR
- **ASR 崩溃**：删除残留空文件，提示手动删除音频缓存后重试
- **部分产物识别**：检查 `run_dir` 下哪些文件存在

## 设计借鉴

| 特性 | 借鉴来源 |
|------|----------|
| 字幕优先策略 | AI-Video-Transcriber |
| CLI 一条命令跑完 | tscribe |
| `doctor` 诊断子命令 | tscribe |
| probe-then-download 模式 | tscribe |
| 本地 mlx-whisper ASR | 原创设计 |
| Agent 自行总结 | 原创设计 |
