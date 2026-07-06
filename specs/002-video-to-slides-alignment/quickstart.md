# Quickstart：video-to-slides 图文对齐修复 端到端验证手册

验证「video-type 分流 + talking_head 段落主导对齐」特性端到端可用，且第一轮 9 个 bug 点已修复。

**前置**：`.venv` 已装依赖（ffmpeg/yt-dlp/mlx-whisper/curl_cffi/opencv/av）；新视频 `BV1MAUsBME6f` 可访问。

**工作目录**：`/Users/jarvis/Documents/VideoToDoc-skills`（下文命令均在此目录执行）。

---

## 1. 单元测试全绿

```bash
.venv/bin/python3 -m pytest \
  .agents/skills/video-to-slides/scripts/videotodoc/tests/test_video_type.py \
  .agents/skills/video-to-slides/scripts/videotodoc/tests/test_frame_selection.py \
  .agents/skills/video-to-slides/scripts/videotodoc/tests/test_align.py \
  .agents/skills/video-to-slides/scripts/videotodoc/tests/test_cli.py \
  -v
```

**预期**：全 PASS。关键断言：

- `TestClassifyByFeatures`：5 种类型阈值边界各返回正确类型
- `TestSceneThresholdByType`：talking_head→0.20 / lecture_slides→0.03 / auto→base
- `TestTrimParagraphDominant`：slide.start_ms/end_ms == 段边界；capture_ms == 段末−500
- `TestParagraphDominantAlign`：section 时间范围 == 段边界，capture 不落中段句
- `TestVideoTypeArg`：Settings.video_type 默认 "auto"

## 2. 现有测试不破（回归门）

```bash
.venv/bin/python3 -m pytest \
  .agents/skills/video-to-slides/scripts/videotodoc/tests/test_align.py \
  .agents/skills/video-to-slides/scripts/videotodoc/tests/test_segment.py \
  .agents/skills/video-to-slides/scripts/videotodoc/tests/test_prepare_merge.py \
  .agents/skills/video-to-slides/scripts/videotodoc/tests/test_review_merge.py \
  -v
```

**预期**：全 PASS。若 `TestAlignSectionsWindowSplit` 因 slide 构造语义变化失败，按段边界新语义更新其 `_slide()` 构造（start/end 显式传段边界）。

## 3. video-type 判型验证（纯函数）

```bash
.venv/bin/python3 -c "
import sys; sys.path.insert(0,'.agents/skills/video-to-slides/scripts')
from videotodoc.slides import _classify_by_features
# talking_head：场景静、边缘少、饱和度低
print('talking_head:', _classify_by_features(0.01, 0.05, 40))
# lecture_slides：场景静、边缘多（PPT文字）
print('lecture_slides:', _classify_by_features(0.02, 0.20, 50))
# movie：场景变化频繁
print('movie:', _classify_by_features(0.40, 0.10, 60))
"
```

**预期**：`talking_head` / `lecture_slides` / `movie_cinematic`。

## 4. 段落主导截图验证（trim 单元）

```bash
.venv/bin/python3 -c "
import sys; sys.path.insert(0,'.agents/skills/video-to-slides/scripts')
from videotodoc.slides import trim_candidates_by_transcript
from videotodoc.models import Slide, SlideSet, Transcript, TranscriptSegment
from videotodoc.config import Settings
from pathlib import Path
seg=TranscriptSegment(start_ms=0,end_ms=22000,text='一段话。')
t=Transcript(backend='reused',language='zh',segments=[seg])
c=SlideSet(slides=[Slide(slide_index=1,image_path='/tmp/c.png',start_ms=0,end_ms=15550,capture_ms=15000,confidence=0.8,hash='0'*16,edge_density=0.05)])
out=trim_candidates_by_transcript(c,t,Path('/tmp/v.mp4'),Path('/tmp/out'),Settings(capture_margin_ms=500))
s=out.slides[0]
assert s.start_ms==0 and s.end_ms==22000, f'段边界错误: {s.start_ms}-{s.end_ms}'
assert s.capture_ms==21500, f'capture错误: {s.capture_ms}'
print('trim 段落主导: OK', s.start_ms, s.end_ms, s.capture_ms)
"
```

**预期**：`trim 段落主导: OK 0 22000 21500`（段边界 + 段末−500，不再是候选窗口 15550）。

## 5. 端到端：新视频 BV1MAUsBME6f

### 5.1 video-summary 下载 + ASR

```bash
.venv/bin/python3 .agents/skills/video-summary/scripts/process.py \
  "https://www.bilibili.com/video/BV1MAUsBME6f/" 2>&1 | tail -20
```

**预期**：退出码 0，产出 `runs/<标题>_<时间戳>/transcript.json` + `transcript.txt`。

**bug 点回归**：
- 卡点 1：命令用完整路径 `.agents/skills/video-summary/scripts/process.py`（不再写 `scripts/process.py`）
- 卡点 2/3：B站风控若仍触发，yt-dlp 回退应成功（browser_cookie3 缺失不影响回退）

### 5.2 video-to-slides 阶段 0：合并碎段

```bash
RUN=$(ls -dt runs/*_<最新时间戳> | head -1)
.venv/bin/python3 .agents/skills/video-to-slides/scripts/videotodoc/prepare_merge.py \
  "$RUN/transcript.json" --archetype topic_preserve
# Agent 合并 → merged_groups.json → apply_merge → review_merge → 注入 self_review
.venv/bin/python3 .agents/skills/video-to-slides/scripts/videotodoc/apply_merge.py \
  "$RUN/transcript.json" "$RUN/merged_groups.json"
.venv/bin/python3 .agents/skills/video-to-slides/scripts/videotodoc/review_merge.py \
  "$RUN/transcript.json" "$RUN/merged_groups.json" -o "$RUN/merge_review_report.json"
.venv/bin/python3 .agents/skills/video-to-slides/scripts/videotodoc/tests/check_review_report.py "$RUN"
```

**预期**：闸口退出码 0。

**bug 点回归**：
- 卡点 4：命令路径无重复 `videotodoc/videotodoc/`
- 卡点 6：review_agent_prompt.md 归属为「video-to-slides 阶段0」（非 video-summary 步骤6）

### 5.3 video-to-slides 阶段 1：截图 + 对齐（核心验证）

```bash
.venv/bin/python3 .agents/skills/video-to-slides/scripts/process.py \
  "$RUN/<视频标题>.mp4" \
  --transcript "$RUN/transcript_merged.json" \
  --run-dir "$RUN" \
  --force-rebuild slides --force-rebuild align 2>&1 | tail -15
```

**预期**：打印 `🎬 视频类型：talking_head`（或实际判型），产出 sections.json + 三份 Markdown。

**核心断言（对齐修复，卡点 9）**：

```bash
.venv/bin/python3 -c "
import json,glob,sys
sys.path.insert(0,'.agents/skills/video-to-slides/scripts')
RUN=sorted(glob.glob('runs/*'))[-1]
secs=json.load(open(glob.glob(RUN+'/cache/*.sections.json')[-1]))['sections']
mi=json.load(open(RUN+'/merge_input.json')); segs={s['index']:s for s in mi['segments']}
mg=json.load(open(RUN+'/merged_groups.json'))
ok=0
for s in secs:
    g=mg[s['segment_indexes'][-1]]; idxs=g['indices']  # 末段索引：capture 属于有 slide 的段
    para_end=segs[idxs[-1]]['end_ms']
    if abs(para_end-s['capture_ms'])<=600: ok+=1
rate=ok/len(secs)
print(f'段末对齐: {ok}/{len(secs)} = {rate:.0%}')
assert rate>=0.9, f'对齐率 {rate:.0%} 未达 90%（旧版仅 26%）'
print('对齐修复: PASS')
"
```

**预期**：`段末对齐: N/N = 9X%` / `对齐修复: PASS`。旧版仅 10/39=26%。

### 5.4 阶段 2 + 3：Agent 整理 + finalize

按 SKILL.md 阶段 2（目录+语义整理+思维导图）+ 阶段 3（finalize.py）执行。

**bug 点回归**：
- 卡点 5：整理版须含 `## 图文讲义` 标题（Agent 补，不再依赖 process.py 生成）

```bash
grep -q '## 图文讲义' "$RUN"/*讲义_整理版*.md && echo '整理版标题: OK' || echo '整理版标题: 缺失'
```

## 6. bug 点回归检查清单

| # | 卡点 | 验证命令 | 预期 |
|---|------|----------|------|
| 1 | video-summary 命令路径 | `grep 'scripts/process.py' .agents/skills/video-summary/SKILL.md` | 无匹配（已改为完整路径） |
| 2 | B站 v_voucher 风控 | 5.1 步下载成功 | yt-dlp 回退成功 |
| 3 | browser_cookie3 缺失 | `grep browser_cookie3 执行报告` | 可选依赖，不影响回退 |
| 4 | merge_procedure 路径 | `grep 'videotodoc/videotodoc' .agents/skills/video-to-slides/reference/merge_procedure.md` | 无匹配 |
| 5 | 整理版缺标题 | `grep '## 图文讲义' <整理版md>` | 有匹配 |
| 6 | review_agent_prompt 归属 | `grep 'video-summary 步骤' .agents/skills/video-to-slides/reference/review_agent_prompt.md` | 无匹配 |
| 7 | shell f-string | — | 使用技巧，非代码（不验） |
| 8 | grep -c 退出码 | — | 使用技巧，非代码（不验） |
| 9 | 图文对齐错位 | 5.3 核心断言 | 段末对齐 ≥ 90% |

## 7. 验收总结

全部通过条件：
1. 单元测试 + 回归测试全绿（第 1、2 节）
2. 新视频端到端跑通，段末对齐率 ≥ 90%（第 5.3 节）
3. bug 点 1/4/5/6/9 回归通过（第 6 节）
4. 截图字幕抽查：末句附近，不再落中段（第 5.3 人工抽查）
