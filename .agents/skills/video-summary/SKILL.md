---
name: video-summary
description: "输入视频链接或本地视频文件路径，自动获取平台字幕（优先）或下载视频后ASR转录，生成文字摘要。触发条件：用户提供视频URL或本地路径并要求下载、转文字、做摘要；或用户说'帮我总结这个视频'、'视频转文字'、'视频摘要'。"
---

# video-summary

视频 → 字幕优先获取（成功则跳过ASR）→ 无字幕时下载视频 → 音频提取 → ASR → 摘要。

## 环境前置

- **网络访问**：下载视频、获取字幕需网络访问权，沙箱内 DNS 不可用时需提权运行
- **ASR 转录**：mlx-whisper 需 Apple Silicon Metal GPU，沙箱内不可用时优雅降级
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
   - 使用 `yt-dlp` 下载视频到 `runs/<视频标题>_<时间戳>/video.mp4`
   - B站需 `curl_cffi` 处理 TLS 指纹

4. **音频提取**（需要 ASR 时）：
   - 使用 `ffmpeg` 从视频提取音频到 `audio.wav`

5. **ASR 转录**（无字幕时）：
   - 默认使用 `mlx-whisper`（Apple Silicon 优化）
   - 生成 `transcript.json`（带时间戳）+ `transcript.txt`（纯文本）

6. **合并转录碎段（必做，不可跳过）**：

**背景**：ASR 按语音停顿把句子切得太碎（平均 1-2 秒一句、半句话一段），
直接用于图文对齐会导致每页只有半句话。**必须**先合并再用于后续步骤。

**步骤**：
1. 运行 prepare_merge 生成合并输入清单（含目标段数建议）：
   python3 .agents/skills/video-summary/scripts/prepare_merge.py \
     runs/<run_dir>/transcript.json
2. 读取 runs/<run_dir>/merge_input.json（含 total_segments、suggestion、segments 清单）
3. 把相邻短句按语义合并为段落，写 runs/<run_dir>/merged_groups.json：
   [{"indices": [0,1,2,3,4,5,6,7,8], "text": "合并后的一段话"}, ...]
4. 运行 apply_merge 校验并落盘：
   python3 .agents/skills/video-summary/scripts/apply_merge.py \
     runs/<run_dir>/transcript.json runs/<run_dir>/merged_groups.json
   失败则按报错修正 merged_groups.json 出错的分组后重跑本步（断点重做，不全量重做）

**合并规则**（严格遵守）：
1. **原文保留**：完整保留每个短句的原文字，不删字、不改字、不加字、不调换顺序。
   你只在短句连接处插入标点。
2. **标点连接**：短句间加合适标点——逗号（停顿/并列/分句）、句号（句末）、
   分号（并列长句）、问号/感叹号（原句语气）、冒号（引出）。保留原问号感叹号。
3. **同话题聚合（最高优先级）**：描述同一件事/同一话题的相邻短句必须整到一段。
   话题转换处断段。宁可段数偏离目标，也要保证同话题完整。
4. **句法完整性（最高优先级）**：禁止把一个完整句子的依存成分拆到两段。
   以下情况必须并入同一段：
   - 程度/数量补语：如“价格暴涨/暴涨了”与“300%到500%”；
   - 数量宾语：如“达到/达到了”与“50亿美元”；
   - 时间/地点状语紧接说明：如“发生在”与“2024年”（由 review agent 按语义复核，客观脚本仅检查数字/百分比等明显补语）；
   - 列举项：同一组并列数据或例子不要拆散。
5. **段数软目标**：参考 `suggestion.target_segments` 和 `suggestion.per_group_range`。
   段数是软目标——同话题完整优先于凑段数。硬上限 `max_segments` 不可超。
6. **每段短句数约束**：尽量使每段包含的短句数落在 `suggestion.per_group_range` 范围内。
   若同话题较长，允许超出，但需在输出前自检并说明理由。
7. **每段字数区间**：每段合并后的中文字符数（含标点）建议落在 `suggestion.chars_per_group_range` 区间内。
   该区间是柔性参考，同话题完整优先；若必须超出，优先在同话题内部切分，而非强行压缩或跨话题拆断。
8. **索引完整**：indices 从 0 连续到末尾，覆盖全部短句，不重不漏；每段内连续递增。

**示例**：
输入：0.Harness这个词最近大火 1.但好像很少有人能说出它的准确定义
      2.但这又不妨碍很多人成天把它挂在嘴边 3.那这件事就比较奇怪了
      4.为什么一个连定义都还没有搞明白的抽象概念 5.会这么火热
      6.甚至代表了一个新的技术方向呢 7.别急
      8.今天这期视频就带你一口气了解Harness的来龙去脉
输出：{"indices": [0,1,2,3,4,5,6,7,8],
       "text": "Harness这个词最近大火，但好像很少有人能说出它的准确定义，但这又不妨碍很多人成天把它挂在嘴边。那这件事就比较奇怪了，为什么一个连定义都还没有搞明白的抽象概念，会这么火热，甚至代表了一个新的技术方向呢？别急，今天这期视频就带你一口气了解Harness的来龙去脉。"}

**注意**：apply_merge 只校验 index 结构（连续覆盖），不校验 text 内容，
所以你整理长句时个别字误差不会报错；只有 index 漏号/跳号/重复才报错，
且报错精确到具体分组，只需修正出错分组重写文件重跑。

### 6.6 Review Agent 复核合并质量

**背景**：整理 agent 第一次合并可能忽略句法依存或字数约束。由另一个独立上下文的 review agent 检查 `merged_groups.json`，输出 `merge_review_report.json`，整理 agent 根据报告局部修正。review agent 不直接修改 `merged_groups.json`，只输出意见；分段决策权始终在 agent。

**步骤**：
1. 整理 agent 完成首次合并后，运行客观检查脚本生成初步报告：
    ```bash
    python3 .agents/skills/video-summary/scripts/review_merge.py \
      runs/<run_dir>/transcript.json runs/<run_dir>/merged_groups.json
    ```
2. review agent 读取：
   - `runs/<run_dir>/merge_input.json`（原始短句 + suggestion 约束）
   - `runs/<run_dir>/merged_groups.json`（整理 agent 输出）
   - `runs/<run_dir>/merge_review_report.json`（客观检查初步结果）
3. review agent 按以下清单复核，输出增强版 `merge_review_report.json`：
   - **句法完整性**：相邻段边界是否把补语/数据/宾语拆散；
   - **同话题聚合**：同一话题是否被不必要地切到两段；
   - **短句数**：每段是否尽量落在 `per_group_range` 内；
   - **字数**：每段是否尽量落在 `chars_per_group_range` 内；
   - **原始短句索引**：是否连续覆盖、无跳号。
4. review report 格式示例：
   ```json
   {
     "total_groups": 69,
     "issues": [
       {
         "group_index": 6,
         "type": "syntax_break",
         "severity": "critical",
         "description": "第6段结尾'价格基本都暴涨了'与第7段开头'300%到500%'是依存关系，应并入同一段",
         "suggested_fix": "整理 agent 将 index 83 并入第7段，或将 index 84-86 并入第6段"
       }
     ],
     "pass": false
   }
   ```

**review agent 规则**：
- 只输出报告，不直接修改 `merged_groups.json`。
- critical 问题必须标记；warning 问题允许整理 agent 酌情处理。
- 所有判断必须基于 `merge_input.json` 中的约束数据，不能自行放宽。
- 遇到超出 `chars_per_group_range` 或 `per_group_range` 的段，先判断是否为“同话题完整”导致；若是，可接受为 warning；若不是，应建议切分。

### 6.7 整理 agent 根据 Review Report 修正

**步骤**：
1. 读取 `merge_review_report.json`；
2. 只修改 report 中标记的问题分组，其余分组保持不变；
3. 修正后重跑 `apply_merge.py` 校验 index；
4. 再次运行 `review_merge.py` 与 review agent，直到 `pass` 为 true 或只剩可接受的 warning；
5. 最终产物为 `transcript_merged.json`。

**修正原则**：
- critical 的 `syntax_break` 必须修复；
- `group_size_exceeded` / `chars_above_max` / `chars_below_min` 优先通过“在同话题内部切分/合并”解决，不要跨话题拆断；
- 若某段因同话题完整而必须超出区间，保留并说明理由。

7. **Agent 摘要**：
   - Agent 读取 `transcript.txt`（合并后的 `transcript_merged.json` 优先）
   - 生成 `<视频标题>_总结_<时间戳>.md`：
     - 提取核心观点和关键信息
     - 按主题分段，使用二级/三级标题
     - 保留重要细节（数字、专有名词、关键论据）
     - 用列表和引用块突出要点

## 默认命令

```bash
# URL 输入（优先获取字幕）
python3 scripts/process.py "https://www.youtube.com/watch?v=xxx"

# 本地视频
python3 scripts/process.py "/path/to/video.mp4"

# 强制跳过字幕，使用 ASR
python3 scripts/process.py "https://www.youtube.com/watch?v=xxx" --no-subtitle

# 诊断依赖
python3 scripts/process.py doctor
```

### 常用参数

```bash
python3 scripts/process.py "<URL>" --language zh
python3 scripts/process.py "<URL>" --no-subtitle    # 跳过字幕，强制 ASR
python3 scripts/process.py "<URL>" --cleanup all     # 清理中间文件
python3 scripts/process.py "/path/to/video.mp4" --output-dir ./runs
```

## 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `input` | （必填） | 视频 URL 或本地文件路径 |
| `--output-dir` | `./runs` | 产物输出目录 |
| `--asr-model` | `mlx-community/whisper-large-v3-turbo` | mlx-whisper 模型 |
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

**注意**：如果成功获取字幕，`video.mp4` 和 `audio.wav` 不会生成。

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
python3 scripts/process.py "<URL>" --proxy "http://127.0.0.1:8080"
```

优先级：命令行 `--proxy` > 环境变量站点映射 > 无代理

## B站支持

B站视频需要 `buvid3/buvid4` 指纹 cookies 才能下载。脚本会自动从 B站 finger API 获取并注入。

当前 B站 playurl API 有 412 反爬问题，这是 yt-dlp 上游的已知问题（PR #16889）。临时解决方案：
- 安装 `curl_cffi`：`pip install curl_cffi`
- **使用代理**：B站下载通常需要代理才能成功，请在命令中添加 `--proxy` 参数：
  ```bash
  python3 scripts/process.py "<B站URL>" --proxy "http://127.0.0.1:7890"
  ```
- 等 yt-dlp 上游修复后升级：`pip install -U yt-dlp`

### B站 412 反爬降级策略

1. curl_cffi buvid cookies（自动）
2. `--cookies-from-browser chrome`（用户指定，从浏览器读取登录态 cookies）
3. v_voucher 检测 → 提示登录

```bash
# 412 时用浏览器 cookies 重试
python3 scripts/process.py "<B站URL>" --cookies-from-browser chrome
```

## 异常处理

- **脚本中途失败**：已有产物会被缓存跳过，重新运行从断点继续
- **字幕下载失败**：自动 fallback 到 ASR
- **ASR 崩溃**：删除残留空文件，提示重试
