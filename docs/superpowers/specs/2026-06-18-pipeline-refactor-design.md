# Pipeline 重构与卡点修复 设计文档

> 来源：2026-06-18 BV13zEg6wEnx 任务复盘。目标：让 video-to-slides 对长视频截图非线性增长、让全流程不踩已知的 9 个坑。

## 一、目标

1. **截图优化**：长视频截图数量不线性增长。30min 视频从 163 页降到 ~45-65 页。
2. **卡点修复**：消除复盘中发现的 9 个"一次性没跑通"的点，让技能首次执行即成功。

## 二、截图优化：三步中断式 pipeline（方案 1）

### 2.1 现状问题

- 固定 15s 间隔截图，30min 视频产生 737 候选 → 去重后仍 163 页。
- trim 阶段对每个无候选图段用 `extract_frame(precise=True)`，每张 15s，28min 视频 trim 耗时 60min+。
- 页数线性增长导致飞书发布时间同步线性增长（163 页串行上传 21min）。

### 2.2 新三步流程

```
capture          review-segments         finalize
─────            ───────────────         ────────
视频+时长 ──→ 候选图 ──→ 分段草案 ──→ agent 确认 ──→ 去重+补图 ──→ Markdown/Word
                ↓          ↓                            ↓
            候选图缓存   pending_segments.json     confirmed_segments.json
                         (脚本启发式生成)           (agent 审查后写回)
```

把现在的 `videotodoc.cli process` 一条命令拆成三个子命令，agent 在 `review-segments` 环节介入。

### 2.3 时长密度函数

根据视频时长动态决定初始截图间隔，替换固定 15s：

```
duration ≤ 5min  → 间隔 15s
duration ≤ 15min → 间隔 20s
duration ≤ 30min → 间隔 30s
duration > 30min → 间隔 40s
```

候选图总数 = duration / 间隔，封顶约 120 张。作用于 `detect_slides` 的 `fallback-interval-sec`。

### 2.4 capture 子命令

**职责**：提取音频、ASR 转录（或复用已有 transcript）、按时长密度截图、生成分段草案。

**输入**：视频路径 + 可选 `--transcript`（复用 video-summary 产物，跳过 ASR）

**产物**：
- `cache/<hash>_<audio>.wav`
- `cache/<hash>_<asr>.transcript.json`
- `cache/<hash>_<interval>.candidates.json`（候选图元数据）
- `slide_candidates/`（候选图文件）
- `pending_segments.json`（分段草案）

**退出语义**：code 0 + stdout 打印 `CAPTURE_DONE` 标记 + pending 文件路径，提示 agent 运行 review-segments。

### 2.5 pending_segments.json 格式

```json
{
  "video_title": "2026年AI办公本推荐...",
  "duration_sec": 1712,
  "capture_interval_sec": 30,
  "segments": [
    {
      "id": "s01",
      "start_ms": 0,
      "end_ms": 49000,
      "label": "开篇：AI办公本市场现状",
      "suggested_action": "keep",
      "candidate_slide_ids": [1, 2, 3],
      "reason": "场景切换 3 次，无重复",
      "transcript_preview": "大家好这里是直选侦探...",
      "char_count": 210
    },
    {
      "id": "s02",
      "start_ms": 49000,
      "end_ms": 95000,
      "label": "选购四大要点",
      "suggested_action": "merge",
      "merge_into": "s01",
      "candidate_slide_ids": [4, 5],
      "reason": "与 s01 同为引言，可合并为'背景+选购要点'",
      "transcript_preview": "首先大家要明白...",
      "char_count": 180
    }
  ]
}
```

`suggested_action` 取值：`keep`（保留独立段）、`merge`（合并到 merge_into 指定段）、`split`（该段过长应拆分）。

### 2.6 分段草案启发式规则（脚本生成 suggested_action）

1. 按候选图场景切换点把视频切成原始片段
2. 合并相邻片段：transcript 文本相似度 ≥0.85，或时长和 < 60s 且无步骤词 → `merge`
3. 标记步骤段：transcript 含"第一步/首先/然后/接下来/操作/步骤"等词且片段 < 20s → 强制 `keep`，不合并
4. 单段文字超 400 字 → `split`，按句号均分
5. 单段文字 < 30 字且无独立场景 → `merge` 到前一段

400 字上限依据：口播 2 分钟约 480-600 字，紧凑化后约 300-380 字，400 留余量。

### 2.7 review-segments 子命令

**职责**：纯本地操作，读取 pending_segments.json 供 agent 审查，agent 编辑后写回 confirmed_segments.json。

**输入**：run_dir（自动找 pending_segments.json）

**行为**：
- 打印 pending_segments.json 内容（表格形式，便于 agent 阅读）
- 校验 agent 写回的 confirmed_segments.json 格式
- 确认无误后退出，提示运行 finalize

**格式校验规则**：
- segments 非空
- 每个 segment 有 id/start_ms/end_ms/label/suggested_action
- merge 的必须带 merge_into，且 merge_into 指向的 segment 存在
- split 的必须带 split_at（拆分时间点 ms）

### 2.8 finalize 子命令

**职责**：按 confirmed_segments.json 做段内去重、补图、生成 Markdown/Word/思维导图。

**输入**：run_dir（自动找 confirmed_segments.json + 候选图）

**前置检查**：confirmed_segments.json 不存在 → 报错并指向 pending 文件。

#### 段内去重

对每个 segment，取其 candidate_slide_ids 对应的候选图，复用现有三段式规则（change_ratio/dHash/OCR），范围收敛到段内：

```
change_ratio < 0.005 且 dHash <= 8  → 合并(留后一张)
change_ratio >= 0.12 或 dHash > 16  → 保留
其余 → OCR 判定(相似度 >= 0.92 且变化面积 < 0.12 → 合并)
保留的图按 capture_ms 排序，作为该 segment 的 selected_slides
```

一个 segment 保留几张图取决于该段内容转折次数——开篇铺垫段可能 3 张候选只剩 1 张，产品对比段可能全保留。

#### 补图逻辑

```
对每个 segment:
  case 1: 去重后 0 张图
    → 段中点快速补一帧(precise=False)
  case 2: 有图但存在"无图覆盖的文字区间"
    → 遍历该段 transcript，找出 [start_ms, end_ms] 内无候选图覆盖的子区间
    → 在该子区间末尾时刻 capture_ms 快速补一帧(precise=False)
    → 补图后重新跑一次段内去重，避免补图与现有图重复
  case 3: 有图且全覆盖
    → 不补
```

case 2 关键：末尾时刻补图，因为讲解走到某点时画面已切到对应内容，末尾帧最贴合。

#### 跨段边界去重

相邻 segment 末帧和首帧可能重复：

```
对相邻 segment 的 [末帧, 下一段首帧] 做 dHash 比较
  若 dHash <= 8 → 删除下一段首帧(保留前一段末帧)
```

只查相邻段，不做全局扫描。

#### cache 复用

```
cache/
├── <hash>_<audio>.wav                          # capture 产物
├── <hash>_<asr>.transcript.json                # capture 产物
├── <hash>_<interval>.candidates.json           # capture 产物
├── <hash>_<interval>.pending_segments.json     # capture 产物
└── <hash>_<interval>.confirmed_segments.json   # finalize 输入(agent 写)
```

`--force-rebuild`：`capture`（重跑截图+ASR+草案）、`finalize`（重跑去重补图，尊重 confirmed）。agent 改完 confirmed 重跑只 `finalize`，不重截图。

### 2.9 页数控制效果预估

| 环节 | 当前 | 新流程预估 |
|------|------|-----------|
| 候选图 | 737 | ~57（30s 间隔） |
| 去重后 | 163 | ~40-60（段内去重 + 语义合并） |
| 补图后 | 163 | ~45-65 |

飞书发布时间同步从 21min 降到约 8min。

## 三、卡点修复

### 3.1 组 I：文档标注类（改 SKILL.md）

| # | 卡点 | 修复 |
|---|------|------|
| 1 | 沙箱内 DNS 不可用 | video-to-slides/video-summary/feishu SKILL.md 顶部加"环境前置"段：下载/ASR/飞书发布需沙箱外或提权运行 |
| 3 | mlx_whisper 沙箱内 RuntimeError | 同上段标注 ASR 需 Metal GPU；doctor 已知问题说明 |
| 8 | lark-cli Keychain 沙箱失败 | feishu SKILL.md 加"发布前确保 lark-cli 登录"前置检查，提示沙箱内需提权或 keychain-downgrade |

### 3.2 组 II：代码 bug 类

| # | 卡点 | 修复 | 文件 |
|---|------|------|------|
| 4 | --transcript 死参数 | process.py 透传 --transcript 到 cli；cli 新增 --transcript，存在则跳过 ASR | process.py + cli.py + pipeline.py |
| 5 | trim precise=True 慢 | 补帧改 precise=False（已改）；新 finalize 补图统一 precise=False | slides.py（已改）+ finalize |
| 6 | lark-cli v1 接口停用 | publish.py 适配 v2（已改）；加版本探测自动选参数 | publish.py（已改）|
| 9 | 截图线性增长 | 新 capture 用时长密度函数 | 新 capture 子命令 |

### 3.3 组 III：架构类

| # | 卡点 | 修复 |
|---|------|------|
| 2 | B 站 v_voucher 风控 | 分层探测多策略（见 3.3.1） |
| 7 | 飞书发布无重试/无断点 | _run 重试（已改）+ 断点续传（见 3.3.2） |

#### 3.3.1 卡点 2：B 站风控分层探测

```
download_video(bilibili_url):
  策略1（首选，无需登录）：
    buvid cookies + playurl API
    → 拿到 dash/durl → 下载
    → 拿到 v_voucher → 进策略2

  策略2（未登录兜底）：
    检测是否 v_voucher 风控
    → 是 → 提示"该视频触发B站风控，需登录态"
         → 尝试 --cookies-from-browser 自动探测(chrome/safari/edge)
         → 探测到登录态 → 下载
         → 探测不到 → 提示"请在浏览器登录B站后重试，或手动提供 cookies"
    → 否(其他错误) → 进策略3

  策略3（yt-dlp 通用）：
    yt-dlp 直接下载(可能 412)
    → 成功 → 完成
    → 412 → 提示"B站反爬，建议 --cookies-from-browser"
```

设计要点：
- 未登录策略始终首选，尊重之前可能有效的路径
- v_voucher 作为明确风控信号单独检测
- 登录态是最后兜底，先自动探测浏览器 cookies
- 网络问题（DNS）和风控问题分开报错，agent 能区分"该提权"还是"该登录"

**待验证**：v_voucher 是否对所有 B 站视频触发。实现阶段需实测不同类型视频确认触发范围。

#### 3.3.2 卡点 7：飞书断点续传

```
publish.py 主流程改为：
  1. create_doc 后写 publish_progress.json: {doc_ref, last_section: 0}
  2. 每发完一个 section，更新 last_section
  3. 重跑时检测 progress.json：
     → doc_ref 存在且文档可访问 → 从 last_section+1 继续
     → 文档不存在(被删) → 新建文档，从头开始
  4. 全部完成后删除 progress.json
```

与已加的重试机制叠加：失败重试→仍失败则断点续传。

## 四、验收标准

### 4.1 截图优化验收

1. 对 30min 测试视频，capture 阶段候选图数 ≤ 120
2. finalize 后总页数 ≤ 80（当前 163）
3. 飞书发布总耗时较当前下降 ≥ 40%
4. capture → review-segments → finalize 三步均可独立重跑，互不重复计算
5. confirmed_segments.json 不存在时 finalize 报错并指向 pending 文件

### 4.2 卡点修复验收

1. `videotodoc process --transcript X.json` 能复用已有转录，不触发 ASR
2. B 站 v_voucher 视频自动提示登录态兜底，未登录视频（若有）仍走策略1
3. lark-cli v1/v2 接口自动适配，发布成功
4. 飞书发布中途失败后重跑，从断点继续而非新建文档
5. doctor 命令在 Metal 不可用时优雅降级而非崩溃
6. 三个 SKILL.md 均含"环境前置"段

### 4.3 回归验收

1. 现有 `videotodoc process` 命令仍可用（向后兼容）
2. 短视频（< 5min）走新流程，页数与旧流程相当
3. 所有新增代码有单元测试覆盖

## 五、范围说明

本设计聚焦 video-to-slides pipeline 重构 + 9 卡点修复。不涉及：
- video-summary 的摘要质量优化
- 思维导图生成逻辑变更
- Word 排版样式调整
