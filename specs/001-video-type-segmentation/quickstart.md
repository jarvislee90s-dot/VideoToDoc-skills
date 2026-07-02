# Quickstart：端到端验证手册

验证"视频类型→转录分段策略"特性端到端可用。前置：`.venv` 已装、`suggest_segments` 旧测试基线绿。

## 1. 向后兼容回归（非协商门）

```bash
cd /Users/jarvis/Documents/VideoToDoc-skills
PYTHONPATH=".agents/skills/video-to-slides/scripts:.agents/skills/_shared" \
  .venv/bin/python3 -m pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_transcript_merge.py::TestSuggestSegments -v
```
**预期**：旧 4 例（test_short_11min/1h/2h/tiny_video_floor）+ 新回归例全 PASS。
关键断言：`suggest_segments(690000)` 仍返回 `target_segments=34, chars_per_group_range="30-120"`。

## 2. 原型策略生效

```bash
.venv/bin/python3 -c "
import sys; sys.path.insert(0,'.agents/skills/_shared')
from transcript_merge import suggest_segments
print(suggest_segments(690_000, archetype='rescan_grid')['chars_per_group_range'])  # 期望 60-220（④）而非 30-120
print(suggest_segments(690_000, archetype='visual_event')['strategy']['visual_required'])  # 期望 required
"
```
**预期**：`60-220` / `required`。

## 3. ③视觉信号降级不崩

```bash
.venv/bin/python3 -c "
import sys; sys.path.insert(0,'.agents/skills/_shared')
from transcript_merge import suggest_segments
s = suggest_segments(690_000, archetype='visual_event', visual_signals=None)
print('warnings:', s.get('warnings'))  # 期望 ['visual_missing']
s2 = suggest_segments(690_000, archetype='visual_event', visual_signals={'slide_boundaries_ms':[1000,5000]})
print('boundaries:', s2['visual_signals']['slide_boundaries_ms'])  # 期望 [1000,5000]
"
```
**预期**：`warnings: ['visual_missing']` / `boundaries: [1000, 5000]`。

## 4. signal_stats 非决策（Constitution I 守护）

```bash
.venv/bin/python3 -c "
import sys; sys.path.insert(0,'.agents/skills/video-summary')
from signal_stats import signal_stats
out = signal_stats('首先点击保存，然后下一步。第三名是X。')
print('archetype' in out, out)  # 期望 False {...计数...}
"
```
**预期**：第一个值 `False`（无 archetype 键），输出为各原型命中计数。

## 5. prepare_merge 端到端

```bash
.venv/bin/python3 .agents/skills/video-summary/scripts/prepare_merge.py \
  "runs/内存暴涨，谁在哭？谁在笑？_20260701_075505/transcript.json" \
  --archetype topic_preserve -o /tmp/pm_out.json
.venv/bin/python3 -c "import json; d=json.load(open('/tmp/pm_out.json')); print(d['suggestion']['archetype'], d['suggestion']['chars_per_group_range'])"
```
**预期**：`topic_preserve 80-320`（①区间）。

### L3 回写验证

```bash
.venv/bin/python3 .agents/skills/video-summary/scripts/prepare_merge.py \
  "runs/内存暴涨，谁在哭？谁在笑？_20260701_075505/transcript.json" \
  --archetype enumeration_unit -o /tmp/pm_enum.json
.venv/bin/python3 -c "import json; print(json.load(open('/tmp/pm_enum.json'))['suggestion']['chars_per_group_range'])"
# 期望 40-160（②），与上面 topic_preserve 的 80-320 不同 → ranges 随 archetype 刷新
```

## 6. ③ e2e（需 video-to-slides 的 slides.json）

```bash
# 取一个 video-to-slides run 的 slides.json 作为视觉信号
.venv/bin/python3 .agents/skills/video-summary/scripts/prepare_merge.py \
  <transcript.json> --archetype visual_event \
  --visual-signals <path/to/slides.json> -o /tmp/pm_vis.json
.venv/bin/python3 -c "import json; d=json.load(open('/tmp/pm_vis.json')); print('boundaries_ms' in d['suggestion'].get('visual_signals',{}))"
```
**预期**：`True`（slide_boundaries_ms 注入成功）。
> 若无可用 video-to-slides run，本项为手动验证；逻辑已由单元测试（quickstart §3）覆盖。

## 7. 全量相关测试

```bash
PYTHONPATH=".agents/skills/video-to-slides/scripts:.agents/skills/_shared:.agents/skills/video-summary/scripts" \
  .venv/bin/python3 -m pytest \
  .agents/skills/video-to-slides/scripts/videotodoc/tests/test_transcript_merge.py \
  .agents/skills/video-summary/scripts/tests/test_review_merge.py \
  .agents/skills/video-summary/scripts/tests/test_strategies.py \
  .agents/skills/video-summary/scripts/tests/test_signal_stats.py -v
```
**预期**：全 PASS。
