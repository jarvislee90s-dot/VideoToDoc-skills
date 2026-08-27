---
name: video-summary
description: "输入视频链接或本地视频文件路径，自动获取平台字幕（优先）或下载视频后ASR转录，生成文字摘要。触发条件：用户提供视频URL或本地路径并要求下载、转文字、做摘要；或用户说'帮我总结这个视频'、'视频转文字'、'视频摘要'。"
---

# video-summary

视频 → 字幕优先获取（成功则跳过ASR）→ 无字幕时下载视频 → 音频提取 → ASR → 摘要。

## 环境前置

- **网络访问**：下载视频、获取字幕需网络访问权，沙箱内 DNS 不可用时需提权运行
- **ASR 转录**：Apple Silicon 上用 `mlx-whisper`（Metal GPU）；Windows/Linux 自动降级到 `faster-whisper`（process.py 自动探测后端，沙箱内不可用时优雅降级）
- **doctor 命令**：Metal 不可用时优雅降级报告，不再崩溃

---

## 工作流

```
输入
 ├─ URL → ① 获取平台字幕（优先）
 │         ├─ 有字幕 → 直接保存为 transcript（跳过视频下载、音频提取、ASR）
 │         └─ 无字幕 → ② 下载视频 → ③ 提取音频 → ④ ASR 转录
 │
 └─ 本地路径 → ③ 提取音频 → ④ ASR 转录
                                    │
                              ⑤ Agent 读取 transcript → 写 summary.md
```

## 详细步骤

1. **输入判断**：
   - URL 输入 → 执行字幕获取（优先）→ 无字幕时下载视频 → ASR
   - 本地路径 → 跳过下载，直接提取音频 + ASR

2. **获取字幕**（仅 URL 输入）：
   - 使用 yt-dlp 探测视频字幕信息
   - 优先人工字幕，其次自动字幕
   - 语言优先级：`zh-Hans > zh > en > 其他`
   - **字幕成功**：直接解析保存为 `transcript.json` + `transcript.txt`，跳过后续步骤
   - **无字幕**：继续下载视频

3. **下载视频**（仅 URL 输入且无字幕时）：
   - 使用 `yt-dlp` 下载视频到 `runs/<视频标题>_<时间戳>/<视频标题>.mp4`
   - B站需 `curl_cffi` 处理 TLS 指纹

4. **音频提取**（需要 ASR 时）：
   - 使用 `ffmpeg` 从视频提取音频到 `audio.wav`

5. **ASR 转录**（无字幕时）：
   - 默认自动探测：Apple Silicon 用 `mlx-whisper`（Metal GPU 优化）；Windows/Linux 用 `faster-whisper`（CPU/GPU 均可）
   - 可用 `--asr-backend` 手动指定，`--asr-model` 指定模型
   - 生成 `transcript.json`（带时间戳）+ `transcript.txt`（纯文本）

6. **Agent 摘要**：
   - Agent 读取 `transcript.txt`
   - 生成 `<视频标题>_总结_<时间戳>.md`：
     - 提取核心观点和关键信息
     - 按主题分段，使用二级/三级标题
     - 保留重要细节（数字、专有名词、关键论据）
     - 用列表和引用块突出要点
   - **注意**：脚本只创建占位 `summary.md`（含明确提示），不会自动生成摘要正文，Agent 必须按上述要点补写

## 默认命令

```bash
# URL 输入（优先获取字幕）
python3 .agents/skills/video-summary/scripts/process.py "https://www.youtube.com/watch?v=xxx"

# 本地视频
python3 .agents/skills/video-summary/scripts/process.py "/path/to/video.mp4"

# 强制跳过字幕，使用 ASR
python3 .agents/skills/video-summary/scripts/process.py "https://www.youtube.com/watch?v=xxx" --no-subtitle

# 诊断依赖
python3 .agents/skills/video-summary/scripts/process.py doctor
```

### 常用参数

```bash
python3 .agents/skills/video-summary/scripts/process.py "<URL>" --language zh
python3 .agents/skills/video-summary/scripts/process.py "<URL>" --no-subtitle    # 跳过字幕，强制 ASR
python3 .agents/skills/video-summary/scripts/process.py "<URL>" --cleanup all     # 清理中间文件
python3 .agents/skills/video-summary/scripts/process.py "/path/to/video.mp4" --output-dir ./runs
```

## 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `input` | （必填） | 视频 URL 或本地文件路径 |
| `--output-dir` | `./runs` | 产物输出目录 |
| `--asr-model` | `mlx-community/whisper-large-v3-turbo` | ASR 模型；faster-whisper 后端自动映射为 openai 模型名（如 `large-v3-turbo`） |
| `--asr-backend` | `auto` | ASR 后端：`auto` 自动探测（默认）、`mlx-whisper`（Apple Silicon）、`faster-whisper`（通用） |
| `--language` | `zh` | 字幕/ASR 语言 |
| `--proxy` | 自动匹配或手动指定 | 代理地址 |
| `--cleanup` | 不清理 | `all`=删音频；`transcript-only`=只保留 summary |
| `--no-subtitle` | flag | 跳过字幕，强制使用 ASR |

## 产物结构

```
runs/<视频标题>_<时间戳>/
├── <视频标题>.mp4                         # 下载的视频（URL 输入且需要 ASR 时）
│                                           # 注意：文件名是视频标题，不是固定的 video.mp4
├── audio.wav                              # 提取的音频（需要 ASR 时）
├── transcript.json                        # 结构化转录（带时间戳）
├── transcript.txt                         # 纯文本转录（Agent 读取）
└── <视频标题>_总结_<时间戳>.md            # Agent 生成的摘要
```

**注意**：如果成功获取字幕，`<视频标题>.mp4` 和 `audio.wav` 不会生成。

### 标题与文件名说明

run_dir 名称与下载的视频文件名都会经过 `_slugify()` 处理：

- 文件系统不安全字符（`/` `:` `?` `*` `<` `>` `"` `|` `\` 等）会被替换为 `_`
- 替换后标题信息可能有损，例如 `Skill/MCP/RAG/Agent/OpenClaw` 会被规范化为 `Skill_MCP_RAG_Agent_OpenClaw`
- 替换仅影响文件/目录命名，不影响 `transcript.json` 中保留的原始视频标题语义
- 实际示例（BV1ojfDBSEPv）：原始标题「【闪客】一口气拆穿Skill/MCP/RAG/Agent/OpenClaw底层逻辑」→ run_dir `【闪客】一口气拆穿Skill_MCP_RAG_Agent_OpenClaw底层逻辑_<时间戳>`

## 与其他 Skill 的关系

- **video-to-slides**：本 Skill 的产物（video + audio + transcript）可直接作为 video-to-slides 的输入。当 video-to-slides 发现缺少视频/音频/字幕时，会建议用户先运行本 Skill。
  ```bash
  # 推荐：复用同一个 run_dir，避免 video-to-slides 再新建文件夹
  python3 .agents/skills/video-to-slides/scripts/process.py \
    "runs/<视频标题>_<时间戳>/<视频标题>.mp4" \
    --transcript "runs/<视频标题>_<时间戳>/transcript.json" \
    --run-dir "runs/<视频标题>_<时间戳>"
  ```
- **feishu-markdown-publish**：如果用户想将 summary.md 发布到飞书，可使用该 Skill。

## 代理配置

通过环境变量 `VIDEO_SUMMARY_PROXY_MAP` 配置站点专属代理：

```bash
export VIDEO_SUMMARY_PROXY_MAP="example.com:127.0.0.1:8080;other.site:127.0.0.1:9090"
```

或命令行直接指定：

```bash
python3 .agents/skills/video-summary/scripts/process.py "<URL>" --proxy "http://127.0.0.1:8080"
```

优先级：命令行 `--proxy` > 环境变量站点映射 > 无代理

## B站支持

B站视频需要 `buvid3/buvid4` 指纹 cookies 才能下载。脚本会自动从 B站 finger API 获取并注入。

当前 B站 playurl API 有 412 反爬问题，这是 yt-dlp 上游的已知问题（PR #16889）。临时解决方案：
- 安装 `curl_cffi`：`pip install curl_cffi`
- **使用代理**：B站下载通常需要代理才能成功，请在命令中添加 `--proxy` 参数：
  ```bash
  python3 .agents/skills/video-summary/scripts/process.py "<B站URL>" --proxy "http://127.0.0.1:7890"
  ```
- 等 yt-dlp 上游修复后升级：`pip install -U yt-dlp`

### B站 412 反爬降级策略

1. curl_cffi buvid cookies（自动）
2. `--cookies-from-browser chrome`（用户指定，从浏览器读取登录态 cookies）
3. v_voucher 检测 → 提示登录

```bash
# 412 时用浏览器 cookies 重试
python3 .agents/skills/video-summary/scripts/process.py "<B站URL>" --cookies-from-browser chrome
```

## 异常处理

- **脚本中途失败**：已有产物会被缓存跳过，重新运行从断点继续
- **字幕下载失败**：自动 fallback 到 ASR
- **ASR 崩溃**：删除残留空文件，提示重试
