# VideoToDoc 碎片化与卡点修复计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 修复 video-to-slides 流水线导致图文讲义"每页一句、385 页碎片化"的根因，并清掉实测 B 站视频过程中暴露的 7 个配套卡点，使一次 `process.py` 调用即可产出页数合理、图文对应正确的讲义。

**架构：** 在「ASR 转录复用」之后、「候选截图」之前，插入一个 LLM 语义合并步骤：把 ASR 按停顿切出的 480 个半句碎段，按语义合并为约 40-60 个完整段落（每段含若干短句、对应一个讲解画面）。LLM 只负责"分组决策"（输出相邻段索引分组），时间戳由代码从原始段精确计算，避免幻觉。合并后下游 `trim_candidates_by_transcript` 按约 50 段补帧，最多补 50 张而非 480 张，碎片化从根源消除。

**技术栈：** Python 3.14、mlx-whisper、RapidOCR、OpenAI Python SDK（仿现有 mindmap 生成先例）、pytest、ffmpeg、yt-dlp。

---

## 背景：实测卡点全览

用 B 站视频 `BV1cNdrB4Evw`（11.5 分钟）实测，从"一次跑通"角度暴露 8 个卡点（1 主 + 7 配套）。本计划逐一修复。

| 编号 | 卡点 | 现象 | 根因文件:行 | 修复任务 |
|------|------|------|-------------|----------|
| ⑧(主) | 图片切太碎 | 385 页每页一句 | `slides.py:trim_candidates_by_transcript` 逐 ASR 段补帧 + ASR 碎段未合并 | 任务 1+2 |
| ⑥ | 转录单位/类型不兼容 | 秒当毫秒、float 传 `:02d` 崩溃 | `pipeline.py:76,158,286` 复用分支 | 任务 2 |
| ⑤ | `_format_ms` float 崩溃 | `ValueError: format code 'd' for float` | `document.py:374` | 任务 3 |
| ④ | slides.py 合并冲突残留 | `IndentationError`，流程直接崩 | `slides.py:570` | 任务 4 |
| ③ | OCR 去重默认值不符 | 文档说默认开，代码默认关 | `config.py:36` 默认 False + `cli.py:50,78` store_true | 任务 5 |
| ⑦ | run_dir 不一致 | video-summary 与 video-to-slides 产物分两个目录 | `pipeline.py` slug 化 + 路径约定 | 任务 6 |
| ② | B 站风控需 cookies | 未登录下载触发 v_voucher | `video-summary/process.py` | 任务 7 |
| ① | 文档命令路径不符 | `skills/...` 实际是 `.agents/skills/...` | 三个 SKILL.md | 任务 8 |

**实测数据（支撑主卡点判断）：** transcript.json 共 480 段，平均时长 1.41s，59% 的段 <1.5s（"别急""你会发现""不废话了"），平均仅 9.8 字。ASR 按停顿切碎 → 下游按 480 段补帧 → 385 页。

---

## 文件结构

**新建：**
- `.agents/skills/_shared/transcript_merge/__init__.py` — 共享合并逻辑（suggest_segments 动态段数、validate_groups 只查 index、apply_groups 重算时间戳、normalize_raw 单位归一化）。不调大模型。
- `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_transcript_merge.py` — 共享逻辑单测（动态段数、index 校验、不查 text）。
- `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_pipeline_transcript.py` — 复用转录路径单测（单位转换、合并链路）。

**修改：**
- `.agents/skills/video-to-slides/scripts/videotodoc/pipeline.py` — 三处复用转录分支：补单位转换（已临时修）+ 调用合并链；`process_video` 在候选截图前插入语义合并。
- `.agents/skills/video-to-slides/scripts/videotodoc/asr.py` — 抽出 `merge_short_segments` 复用到复用路径；或直接在 pipeline 复用分支补调 normalize+merge。
- `.agents/skills/video-to-slides/scripts/videotodoc/config.py` — `ocr_dedupe` 默认改 True（任务5）。
- `.agents/skills/video-to-slides/scripts/videotodoc/document.py:374` — `_format_ms` 类型防御（已临时修根因，补防御）。
- `.agents/skills/video-to-slides/scripts/videotodoc/slides.py:570` — 清理合并冲突（已临时修，加防回归）。
- `.agents/skills/video-to-slides/scripts/videotodoc/cli.py` — `--ocr-dedupe` 默认 True；新增 `--no-merge-transcript`。
- `.agents/skills/video-summary/scripts/process.py` — B 站默认尝试浏览器 cookies。
- 三个 `SKILL.md` — 修正命令路径为 `.agents/skills/...`。

**设计原则：** LLM 只做语义分组决策（输出 `[[0,1,2],[3,4],...]` 相邻索引组），时间戳/文字拼接由代码从原始段计算，确保时间精确、可回退、可单测（mock LLM 返回）。

---

## 任务 1：语义合并脚本工具（共享模块 + CLI，不调大模型）（修复主卡点⑧）

**目标：** 提供两个纯 IO/计算脚本，把"语义判断"完全留给执行 skill 的 agent，脚本只做：①算目标段数建议、②校验 agent 输出的分组 index、③按分组精确重算时间戳落盘。**脚本绝不调用大模型。**

**职责分离：**
- agent 负责：读 `transcript.json` → 语义分组 + 在短句间加标点 + 整合同话题 → 写 `merged_groups.json`
- 脚本负责：校验 index 结构（**只查 index，不查 text**）→ 用组首 `start_ms`/组尾 `end_ms` 算时间戳 → 写 `transcript_merged.json`

**流向：**
```
transcript.json (ASR输出，碎段带时间戳)
   ↓ agent 直接读，语义整理
merged_groups.json (agent 产物：[{indices:[..], text:".."}])
   ↓ apply_merge.py 校验 index + 重算时间戳
transcript_merged.json (毫秒时间戳，供 video-to-slides 消费)
```

**文件：**
- 创建：`.agents/skills/_shared/transcript_merge/__init__.py` — 共享逻辑（suggest_segments、validate_groups、apply_groups）
- 创建：`.agents/skills/video-summary/scripts/prepare_merge.py` — 薄 CLI：读 transcript.json → 输出合并建议（目标段数）+ 带 index 短句清单到 `merge_input.json`，供 agent 参考
- 创建：`.agents/skills/video-summary/scripts/apply_merge.py` — 薄 CLI：校验 `merged_groups.json` + 落盘 `transcript_merged.json`
- 创建测试：`.agents/skills/video-to-slides/scripts/videotodoc/tests/test_transcript_merge.py`（`_shared` 已在 pytest pythonpath）

### 设计要点

- **动态段数**：按视频时长决定目标段数（见下表），脚本算好写进 `merge_input.json` 的 `suggestion` 字段告诉 agent。段数是软目标，"同话题整成一段"优先级最高。
- **校验只查 index**：覆盖 `0..N-1` 无缺漏无重复、每组内连续递增。**不查 text**，agent 长句整理个别字误差不报错。
- **断点重做**：校验失败时报错精确到"缺 index 47 / 第9组不连续"，agent 只改出错分组重写 `merged_groups.json` 重跑 `apply_merge.py`，不全量重新语义分析。
- **复用**：共享逻辑放 `_shared/transcript_merge`，video-summary 与 video-to-slides 都 import；CLI 薄包装放各 skill scripts 下。

**动态段数表（suggest_segments 实现）：**

| 视频时长 | 单段时长 | 每段短句数 | 段数硬上限 |
|---------|---------|-----------|-----------|
| ≤15min | ~20s | 3-8 | 120 |
| ≤30min | ~30s | 5-12 | 120 |
| ≤60min | ~40s | 8-18 | 120 |
| >60min | ~50s | 12-25 | 时长分钟×2（1h=120） |

- [ ] **步骤 1：编写失败的单测（动态段数 + index 校验）**

创建 `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_transcript_merge.py`：

```python
from transcript_merge import suggest_segments, validate_groups


class TestSuggestSegments:
    def test_short_11min(self):
        s = suggest_segments(690_000)  # 11.5min
        assert s["target_segments"] == 34
        assert s["per_group_range"] == "3-8"
        assert s["max_segments"] == 120

    def test_1h(self):
        s = suggest_segments(3_600_000)
        assert s["target_segments"] == 90
        assert s["max_segments"] == 120

    def test_2h_cap(self):
        s = suggest_segments(7_200_000)
        assert s["max_segments"] == 240  # 120min*2
        assert s["target_segments"] == 144  # 7200/50

    def test_tiny_video_floor(self):
        s = suggest_segments(60_000)  # 1min
        assert s["target_segments"] >= 8


class TestValidateGroups:
    def test_valid_cover(self):
        groups = [{"indices": [0, 1, 2]}, {"indices": [3, 4]}]
        ok, _ = validate_groups(groups, 5)
        assert ok is True

    def test_missing_index(self):
        groups = [{"indices": [0, 1]}, {"indices": [3, 4]}]  # 缺2
        ok, detail = validate_groups(groups, 5)
        assert ok is False
        assert "2" in detail

    def test_non_contiguous_in_group(self):
        groups = [{"indices": [0, 2]}, {"indices": [1, 3, 4]}]  # 第0组跳号
        ok, detail = validate_groups(groups, 5)
        assert ok is False
        assert "不连续" in detail

    def test_duplicate(self):
        groups = [{"indices": [0, 1, 1]}, {"indices": [2, 3, 4]}]  # 1重复
        ok, detail = validate_groups(groups, 5)
        assert ok is False

    def test_text_never_checked(self):
        # text 随便写甚至缺失都不影响校验（只查 index）
        groups = [{"indices": [0, 1], "text": ""}, {"indices": [2, 3, 4], "text": "完全无关的错字"}]
        ok, _ = validate_groups(groups, 5)
        assert ok is True
```

- [ ] **步骤 2：运行测试验证失败**

运行：`.venv/bin/python3 -m pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_transcript_merge.py -v`
预期：FAIL，`ModuleNotFoundError: No module named 'transcript_merge'`

- [ ] **步骤 3：实现共享模块**

创建 `.agents/skills/_shared/transcript_merge/__init__.py`：

```python
"""转录碎段语义合并的共享逻辑（不调大模型）。

agent 负责语义分组与文字整理，脚本只算目标段数建议、校验 index 结构、
重算时间戳。校验只查 index，不查 text。
"""
from __future__ import annotations


def suggest_segments(duration_ms: int) -> dict:
    """按视频时长决定目标段数建议。段数为软目标，同话题完整优先。"""
    duration_sec = duration_ms / 1000
    duration_min = duration_sec / 60
    if duration_min <= 15:
        target = max(8, int(duration_sec / 20))
        per_group = "3-8"
    elif duration_min <= 30:
        target = max(12, int(duration_sec / 30))
        per_group = "5-12"
    elif duration_min <= 60:
        target = max(20, int(duration_sec / 40))
        per_group = "8-18"
    else:
        target = max(30, int(duration_sec / 50))
        per_group = "12-25"
    max_seg = int(duration_min * 2) if duration_min > 60 else 120
    target = min(target, max_seg)
    return {"target_segments": target, "per_group_range": per_group, "max_segments": max_seg}


def validate_groups(groups: list, n_segments: int) -> tuple[bool, str]:
    """只校验 index 结构：覆盖 0..n-1 无缺漏无重复、每组内连续递增。不查 text。"""
    if not isinstance(groups, list) or not groups:
        return False, "分组为空或非列表"
    flat: list[int] = []
    for gi, g in enumerate(groups):
        idx = g.get("indices") if isinstance(g, dict) else None
        if not isinstance(idx, list) or not idx:
            return False, f"第{gi}组缺 indices"
        for k in range(1, len(idx)):
            if idx[k] != idx[k - 1] + 1:
                return False, f"第{gi}组 indices 不连续：{idx}"
        flat.extend(idx)
    if sorted(flat) != list(range(n_segments)):
        miss = sorted(set(range(n_segments)) - set(flat))
        dup = sorted({x for x in flat if flat.count(x) > 1})
        parts = []
        if miss:
            parts.append(f"缺失{miss[:10]}")
        if dup:
            parts.append(f"重复{dup[:10]}")
        return False, "；".join(parts)
    return True, ""


def apply_groups(raw_segments: list[dict], groups: list[dict]) -> list[dict]:
    """按分组重算时间戳：组首 start_ms → 组尾 end_ms。text 用 agent 输出。"""
    merged: list[dict] = []
    for g in groups:
        idx = g["indices"]
        merged.append({
            "start_ms": raw_segments[idx[0]]["start_ms"],
            "end_ms": raw_segments[idx[-1]]["end_ms"],
            "text": g.get("text", ""),
        })
    return merged


def normalize_raw(raw: list[dict]) -> list[dict]:
    """归一化原始段：兼容 秒·float / 毫秒·int 两种格式（卡点⑥根因）。"""
    out = []
    for s in raw:
        if "start_ms" in s:
            sms, ems = int(s["start_ms"]), int(s["end_ms"])
        else:
            sms = int(round(float(s.get("start", 0)) * 1000))
            ems = int(round(float(s.get("end", 0)) * 1000))
        out.append({"start_ms": sms, "end_ms": ems, "text": s.get("text", "")})
    return out
```

- [ ] **步骤 4：实现 prepare_merge.py CLI**

创建 `.agents/skills/video-summary/scripts/prepare_merge.py`：

```python
#!/usr/bin/env python3
"""准备语义合并：读 transcript.json → 输出 merge_input.json（目标段数建议 + 带 index 短句清单）。
不调大模型。供 agent 读取后做语义分组。"""
from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_shared"))
from transcript_merge import suggest_segments, normalize_raw  # noqa: E402


def main(transcript_path: str, out_path: str | None = None) -> None:
    data = json.loads(Path(transcript_path).read_text(encoding="utf-8"))
    raw = data if isinstance(data, list) else data.get("segments", [])
    segs = normalize_raw(raw)
    for i, s in enumerate(segs):
        s["index"] = i
    duration_ms = segs[-1]["end_ms"] if segs else 0
    suggestion = suggest_segments(duration_ms)
    out = {
        "total_segments": len(segs),
        "duration_ms": duration_ms,
        "suggestion": suggestion,
        "segments": segs,
    }
    out_path = out_path or str(Path(transcript_path).parent / "merge_input.json")
    Path(out_path).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  📝 合并输入清单：{out_path}")
    print(f"     共 {len(segs)} 碎句，时长 {duration_ms/1000:.0f}s，建议目标约 {suggestion['target_segments']} 段")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript")
    ap.add_argument("-o", "--output", default=None)
    a = ap.parse_args()
    main(a.transcript, a.output)
```

- [ ] **步骤 5：实现 apply_merge.py CLI**

创建 `.agents/skills/video-summary/scripts/apply_merge.py`：

```python
#!/usr/bin/env python3
"""校验 agent 输出的 merged_groups.json，重算时间戳，写 transcript_merged.json。
只校验 index（不查 text）。校验失败精确报错，agent 局部修正后重跑。"""
from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_shared"))
from transcript_merge import validate_groups, apply_groups, normalize_raw  # noqa: E402


def main(transcript_path: str, groups_path: str, out_path: str | None = None) -> int:
    data = json.loads(Path(transcript_path).read_text(encoding="utf-8"))
    raw = data if isinstance(data, list) else data.get("segments", [])
    segs = normalize_raw(raw)
    groups = json.loads(Path(groups_path).read_text(encoding="utf-8"))
    ok, detail = validate_groups(groups, len(segs))
    if not ok:
        print(f"  ❌ 合并分组校验失败：{detail}", file=sys.stderr)
        print("  请修正 merged_groups.json 中出错的分组（只改 index），重跑本命令", file=sys.stderr)
        return 1
    merged = apply_groups(segs, groups)
    out = {"backend": "merged", "language": "zh", "segments": merged}
    out_path = out_path or str(Path(transcript_path).parent / "transcript_merged.json")
    Path(out_path).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✅ 合并完成：{len(segs)} 碎段 → {len(merged)} 段 → {out_path}")
    return 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript")
    ap.add_argument("groups")
    ap.add_argument("-o", "--output", default=None)
    a = ap.parse_args()
    sys.exit(main(a.transcript, a.groups, a.output))
```

- [ ] **步骤 6：运行测试验证通过**

运行：`.venv/bin/python3 -m pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_transcript_merge.py -v`
预期：9 个测试全部 PASS

- [ ] **步骤 7：Commit**

```bash
git add .agents/skills/_shared/transcript_merge/__init__.py \
        .agents/skills/video-summary/scripts/prepare_merge.py \
        .agents/skills/video-summary/scripts/apply_merge.py \
        .agents/skills/video-to-slides/scripts/videotodoc/tests/test_transcript_merge.py
git commit -m "feat: 转录语义合并脚本工具（不调大模型，校验只查 index）"
```

---

## 任务 2：SKILL.md 增设 agent 语义合并步骤 + pipeline 复用合并版（修复卡点⑥⑧）

**目标：** 在 video-summary 的 SKILL.md 流程里加一个 agent 步骤（⑤.5），由执行 skill 的 agent 读 transcript.json 做语义合并；video-to-slides 单独调用时若拿到未合并的 transcript，也复用同一 agent 步骤。pipeline 复用转录时优先读 `transcript_merged.json`，并修复单位转换（卡点⑥）。

**文件：**
- 修改：`.agents/skills/video-summary/SKILL.md` — 新增 ⑤.5 Agent 合并碎段（含提示词、动态段数规则、断点重做）
- 修改：`.agents/skills/video-to-slides/SKILL.md` — 阶段0复用语义合并；默认命令路径修正（见任务8合并执行）
- 修改：`.agents/skills/video-to-slides/scripts/videotodoc/pipeline.py:76,158,286` — 三处复用分支：抽公共函数修单位转换（卡点⑥）；优先读 `transcript_merged.json`
- 创建测试：`.agents/skills/video-to-slides/scripts/videotodoc/tests/test_pipeline_transcript.py`

### 提示词（写进 video-summary SKILL.md 的 ⑤.5）

```markdown
### ⑤.5 Agent 合并转录碎段

**背景**：ASR 按语音停顿把句子切得太碎（平均 1-2 秒一句、半句话一段），
直接用于图文对齐会导致每页只有半句话。需要你把碎段按语义合并成完整段落。

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
4. **段数软目标**：参考 suggestion.target_segments 和 per_group_range。
   段数是软目标——同话题完整优先于凑段数。硬上限 max_segments 不可超。
5. **索引完整**：indices 从 0 连续到末尾，覆盖全部短句，不重不漏；每段内连续递增。

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
```

- [ ] **步骤 1：抽取复用转录公共函数（修卡点⑥根因）**

在 `pipeline.py` 顶部新增，替换 `:76,:158,:286` 三处重复内联构造：

```python
def _transcript_from_external(data: object, language: str) -> "Transcript":
    """从外部 transcript 构造，兼容 秒·float / 毫秒·int（卡点⑥根因）。"""
    from .models import Transcript, TranscriptSegment
    items = data if isinstance(data, list) else data.get("segments", [])  # type: ignore[union-attr]
    segs = [TranscriptSegment(
        start_ms=int(s["start_ms"]) if "start_ms" in s else int(round(float(s.get("start", 0)) * 1000)),
        end_ms=int(s["end_ms"]) if "end_ms" in s else int(round(float(s.get("end", 0)) * 1000)),
        text=s.get("text", ""),
    ) for s in items]
    return Transcript(backend="reused", language=language, segments=segs)
```

三处替换为 `transcript = _transcript_from_external(data, settings.language)`。

- [ ] **步骤 2：pipeline 优先读 transcript_merged.json**

修改 `process_video` 步骤2 复用分支，在读取 `settings.transcript_path` 前先探测同目录 `transcript_merged.json`：

```python
    # 步骤 2：ASR 转录（优先合并版）
    if settings.transcript_path:
        from .io import read_json
        tpath = Path(settings.transcript_path)
        merged_path = tpath.parent / "transcript_merged.json"
        source_path = merged_path if merged_path.exists() else tpath
        if merged_path.exists():
            print(f"  ♻️  使用已合并转录：{merged_path.name}")
        transcript = _transcript_from_external(read_json(source_path), settings.language)
        print(f"  ♻️  转录段数：{len(transcript.segments)}")
    else:
        transcript = transcribe_audio(audio, transcript_path, settings, force=_stage_forced(force_rebuild, "asr"))
```

> 合并版已 ~34 段，下游 `trim_candidates_by_transcript` 补帧量从 480 降到 ~34，碎片化从根源消除。`trim` 逐段补帧逻辑保留（合并后段数少，补帧可控）。

- [ ] **步骤 3：编写复用路径单测（固化卡点⑥修复 + 优先合并版）**

创建 `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_pipeline_transcript.py`：

```python
from videotodoc.pipeline import _transcript_from_external


class TestTranscriptFromExternal:
    def test_seconds_float_list(self):
        data = [{"start": 1.5, "end": 3.0, "text": "hi"}, {"start": 3.0, "end": 4.5, "text": "ok"}]
        t = _transcript_from_external(data, "zh")
        assert t.segments[0].start_ms == 1500
        assert t.segments[0].end_ms == 3000
        assert isinstance(t.segments[0].start_ms, int)

    def test_ms_dict_segments(self):
        data = {"segments": [{"start_ms": 1000, "end_ms": 2000, "text": "x"}]}
        t = _transcript_from_external(data, "zh")
        assert t.segments[0].start_ms == 1000

    def test_empty(self):
        assert _transcript_from_external([], "zh").segments == []
```

- [ ] **步骤 4：运行测试 + 端到端验证**

```bash
.venv/bin/python3 -m pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_pipeline_transcript.py \
  .agents/skills/video-to-slides/scripts/videotodoc/tests/test_transcript_merge.py -v
```

端到端（agent 先做 ⑤.5 合并，再跑 video-to-slides）：
```bash
# 1. prepare
.venv/bin/python3 .agents/skills/video-summary/scripts/prepare_merge.py \
  "runs/【闪客】..._20260618_223122/transcript.json"
# 2. agent 读 merge_input.json 写 merged_groups.json（按提示词）
# 3. apply
.venv/bin/python3 .agents/skills/video-summary/scripts/apply_merge.py \
  "runs/【闪客】..._20260618_223122/transcript.json" \
  "runs/【闪客】..._20260618_223122/merged_groups.json"
# 4. video-to-slides 用合并版
.venv/bin/python3 .agents/skills/video-to-slides/scripts/process.py \
  "runs/【闪客】..._20260618_223122/【闪客】...mp4" \
  --transcript "runs/【闪客】..._20260618_223122/transcript.json" \
  --capture-mode audit --force-rebuild asr
```
预期：video-to-slides 日志 `使用已合并转录`，整理版 MD 页数 ~34（而非 385）。

- [ ] **步骤 5：Commit**

```bash
git add .agents/skills/video-summary/SKILL.md \
        .agents/skills/video-to-slides/SKILL.md \
        .agents/skills/video-to-slides/scripts/videotodoc/pipeline.py \
        .agents/skills/video-to-slides/scripts/videotodoc/tests/test_pipeline_transcript.py
git commit -m "feat: SKILL.md 增设 agent 语义合并步骤，pipeline 优先用合并版转录"
```

---

## 任务 3：`_format_ms` float 防御（修复卡点⑤）

**目标：** 即便上游传入 float 毫秒，`_format_ms` 也不崩。根因已在任务2修复（单位转换），本任务加防御兜底。

**文件：**
- 修改：`.agents/skills/video-to-slides/scripts/videotodoc/document.py:368-374`
- 修改测试：`.agents/skills/video-to-slides/scripts/videotodoc/tests/`（新增 test_document.py 若无）

- [ ] **步骤 1：编写失败测试**

创建 `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_document.py`：

```python
from videotodoc.document import _format_ms


class TestFormatMs:
    def test_int_ms(self):
        assert _format_ms(90000) == "01:30"

    def test_float_ms_does_not_crash(self):
        assert _format_ms(90000.0) == "01:30"

    def test_zero(self):
        assert _format_ms(0) == "00:00"

    def test_negative_clamps(self):
        assert _format_ms(-100) == "00:00"
```

- [ ] **步骤 2：运行验证失败**

运行：`.venv/bin/python3 -m pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_document.py::TestFormatMs -v`
预期：`test_float_ms_does_not_crash` FAIL（`ValueError`）

- [ ] **步骤 3：实现防御**

修改 `document.py:368`：

```python
def _format_ms(value: int) -> str:
    seconds = max(0, int(value)) // 1000
    minutes, sec = divmod(seconds, 60)
    hours, minute = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minute:02d}:{sec:02d}"
    return f"{minute:02d}:{sec:02d}"
```

- [ ] **步骤 4：运行验证通过 + Commit**

```bash
.venv/bin/python3 -m pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/test_document.py -v
git add .agents/skills/video-to-slides/scripts/videotodoc/document.py \
        .agents/skills/video-to-slides/scripts/videotodoc/tests/test_document.py
git commit -m "fix(videotodoc): _format_ms 对 float/负数做防御"
```

---

## 任务 4：清理合并冲突残留 + 防回归（修复卡点④）

**目标：** slides.py 的 git 合并冲突标记已临时清理，本任务加 CI 检查防止再次残留。

**文件：**
- 修改：`.agents/skills/video-to-slides/scripts/videotodoc/slides.py:570`（已清理，确认）
- 新增脚本：`scripts/check_conflict_markers.sh`

- [ ] **步骤 1：确认无残留**

运行：`rg -n "^(<<<<<<<|=======|>>>>>>>)" .agents/skills/ && echo FOUND || echo CLEAN`
预期：`CLEAN`

- [ ] **步骤 2：新增冲突标记检查脚本**

创建 `scripts/check_conflict_markers.sh`：

```bash
#!/usr/bin/env bash
# 防止 git 合并冲突标记残留进入仓库
set -euo pipefail
if rg -n "^(<<<<<<< |=======|>>>>>>> )" .agents/skills/ 2>/dev/null; then
  echo "❌ 发现 git 合并冲突标记残留" >&2
  exit 1
fi
echo "✅ 无冲突标记残留"
```

- [ ] **步骤 3：运行脚本验证 + Commit**

```bash
chmod +x scripts/check_conflict_markers.sh
bash scripts/check_conflict_markers.sh
git add scripts/check_conflict_markers.sh
git commit -m "chore: 新增合并冲突标记检查脚本"
```

---

## 任务 5：OCR 去重默认开启（修复卡点③）

**目标：** SKILL.md 称 OCR 去重默认开启，但 `--ocr-dedupe` 是 `store_true`（默认关）。改为默认开，新增 `--no-ocr-dedupe` 关闭。

**文件：**
- 修改：`.agents/skills/video-to-slides/scripts/videotodoc/config.py`（`ocr_dedupe` 默认 True）
- 修改：`.agents/skills/video-to-slides/scripts/videotodoc/cli.py:50,78`（`--ocr-dedupe` → `--no-ocr-dedupe`）
- 修改：`.agents/skills/video-to-slides/scripts/videotodoc/cli.py:203`（`_settings_from_args` 逻辑反转）

- [ ] **步骤 1：config.py 默认 True**

确认/修改 `config.py` 中 `ocr_dedupe` 字段默认值为 `True`（若不存在则新增 `ocr_dedupe: bool = True`）。

- [ ] **步骤 2：cli.py 反转开关语义**

把 `cli.py:50` 和 `:78` 的：

```python
    process.add_argument("--ocr-dedupe", action="store_true")
```

改为：

```python
    process.add_argument("--no-ocr-dedupe", action="store_true",
                         help="关闭 OCR 辅助去重（白底 PPT 易误合并，不建议）")
```

把 `_settings_from_args`（`:203`）的：

```python
    if getattr(args, "ocr_dedupe", False):
        settings.ocr_dedupe = True
```

改为：

```python
    if getattr(args, "no_ocr_dedupe", False):
        settings.ocr_dedupe = False
```

- [ ] **步骤 3：验证 + Commit**

```bash
.venv/bin/python3 -c "from videotodoc.config import Settings; assert Settings().ocr_dedupe is True; print('默认开启 OK')"
git add .agents/skills/video-to-slides/scripts/videotodoc/config.py \
        .agents/skills/video-to-slides/scripts/videotodoc/cli.py
git commit -m "fix(videotodoc): OCR 去重默认开启，与文档一致"
```

---

## 任务 6：run_dir 一致性（修复卡点⑦）

**目标：** video-summary 用原标题建 run_dir（含【】！？），video-to-slides 内部 slugify 后建新 run_dir，产物分两处。让 video-to-slides 优先复用 video-summary 的 run_dir，或至少明确传递路径。

**现状：** video-summary 产物在 `runs/<原标题>_<ts>/`，含 `transcript.json` + `<原标题>.mp4`；video-to-slides 用 `--transcript` 时仍按 `slugify(video_path.stem)` 建自己的 run_dir，找不到视频文件约定。

**方案（最小改动）：** video-to-slides 接受 `--run-dir` 显式指定输出目录，复用 video-summary 的 run_dir。当传了 `--transcript` 且其所在目录有同名 `.mp4` 时，默认把产物写进该目录。

**文件：**
- 修改：`.agents/skills/video-to-slides/scripts/videotodoc/cli.py:41`（新增 `--run-dir`）
- 修改：`.agents/skills/video-to-slides/scripts/videotodoc/pipeline.py:243`（run_dir 来源逻辑）

- [ ] **步骤 1：cli.py 新增 `--run-dir`**

在 `process` 子命令 `--runs-dir` 后新增：

```python
    process.add_argument("--run-dir", type=Path, default=None,
                         help="显式指定输出目录（复用 video-summary 的 run_dir）")
```

`_process` 透传：

```python
def _process(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    result = process_video(args.video, args.runs_dir, settings, set(args.force_rebuild),
                           run_dir=args.run_dir)
```

- [ ] **步骤 2：pipeline.py process_video 支持 run_dir 参数**

修改 `process_video` 签名与开头：

```python
def process_video(
    video_path: Path,
    runs_dir: Path,
    settings: Settings,
    force_rebuild: set[str] | None = None,
    run_dir: Path | None = None,
) -> ProcessResult:
    ensure_file(video_path, "视频文件")
    force_rebuild = force_rebuild or set()

    if run_dir is not None:
        run_dir = run_dir.resolve()
    else:
        slug = slugify(video_path.stem)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = runs_dir / f"{slug}_{ts}"
    cache_dir = run_dir / "cache"
    run_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    # 产物文件名仍用 slugify（文件系统安全），但目录复用外部 run_dir
    slug = slugify(video_path.stem)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
```

- [ ] **步骤 3：端到端验证 + Commit**

```bash
.venv/bin/python3 .agents/skills/video-to-slides/scripts/process.py \
  "runs/【闪客】..._20260618_223122/【闪客】你管这破玩意叫 Harness？虚拟世界的牛马套餐！.mp4" \
  --transcript "runs/【闪客】..._20260618_223122/transcript.json" \
  --run-dir "runs/【闪客】..._20260618_223122" \
  --capture-mode audit --ocr-dedupe --force-rebuild asr
```
预期：产物写进 video-summary 的 run_dir，不再新建 `闪客_...` 目录。

```bash
git add .agents/skills/video-to-slides/scripts/videotodoc/cli.py \
        .agents/skills/video-to-slides/scripts/videotodoc/pipeline.py
git commit -m "feat(videotodoc): 支持 --run-dir 复用 video-summary 产物目录"
```

---

## 任务 7：B 站风控默认带浏览器 cookies（修复卡点②）

**目标：** 未登录态下载 B 站视频触发 v_voucher 风控，需 `--cookies-from-browser chrome`。让 video-summary 在风控时自动回退到浏览器 cookies，或在交互环境默认尝试。

**现状：** `download_video` 已实现"策略2：浏览器 cookies 重试"（实测成功），但首次未登录态必失败一次再回退，浪费一轮。方案：检测到 `BILI_V_VOUCHER_NEED_LOGIN` 时立即用浏览器 cookies 重试，并把 `--cookies-from-browser` 默认设为 `chrome`（macOS 最常见）。

**文件：**
- 修改：`.agents/skills/video-summary/scripts/process.py:560-580`（download_video 风控处理）和 argparse 默认值

- [ ] **步骤 1：argparse 默认 cookies-from-browser=chrome**

修改 `process.py` 的 argparse（约 840 行 `--cookies-from-browser`）：

```python
    parser.add_argument("--cookies-from-browser", default="chrome",
                        choices=["chrome", "firefox", "safari", "edge"],
                        help="浏览器 cookies 来源（默认 chrome，B 站风控需登录态）")
```

- [ ] **步骤 2：风控时立即回退而非先失败一轮**

确认 `download_video` 中 `BILI_V_VOUCHER_NEED_LOGIN` 分支已调用浏览器 cookies 策略（实测已工作）。若未默认带 cookies 导致首轮必失败，在调用 `download_video` 前先尝试带 cookies，省一轮。具体：`cmd_process` 中 `download_video(...)` 调用已透传 `cookies_from_browser`，步骤1默认值生效后首轮即带 cookies。

- [ ] **步骤 3：验证 + Commit**

```bash
.venv/bin/python3 .agents/skills/video-summary/scripts/process.py "https://www.bilibili.com/video/BV1cNdrB4Evw/" --language zh 2>&1 | grep -E "下载视频流|风控|✅"
git add .agents/skills/video-summary/scripts/process.py
git commit -m "fix(video-summary): 默认带 chrome cookies，避免 B 站风控首轮失败"
```

---

## 任务 8：修正 SKILL.md 命令路径（修复卡点①）

**目标：** 三个 SKILL.md 的默认命令写 `skills/<skill>/scripts/...`，实际是 `.agents/skills/<skill>/scripts/...`，首次运行直接 No such file。

**文件：**
- 修改：`.agents/skills/video-summary/SKILL.md`
- 修改：`.agents/skills/video-to-slides/SKILL.md`
- 修改：`.agents/skills/feishu-markdown-publish/SKILL.md`

- [ ] **步骤 1：批量替换路径前缀**

对三个 SKILL.md，把命令中的 `skills/video-summary/scripts/`、`skills/video-to-slides/scripts/`、`skills/feishu-markdown-publish/scripts/` 替换为 `.agents/skills/...`。

```bash
for f in .agents/skills/video-summary/SKILL.md \
         .agents/skills/video-to-slides/SKILL.md \
         .agents/skills/feishu-markdown-publish/SKILL.md; do
  sed -i '' 's#skills/video-summary/scripts/#.agents/skills/video-summary/scripts/#g' "$f"
  sed -i '' 's#skills/video-to-slides/scripts/#.agents/skills/video-to-slides/scripts/#g' "$f"
  sed -i '' 's#skills/feishu-markdown-publish/scripts/#.agents/skills/feishu-markdown-publish/scripts/#g' "$f"
done
rg -n "python3 skills/" .agents/skills/*/SKILL.md && echo "仍有遗漏" || echo "全部修正"
```

- [ ] **步骤 2：验证命令可执行 + Commit**

```bash
.venv/bin/python3 .agents/skills/video-to-slides/scripts/process.py --help >/dev/null && echo "路径有效"
git add .agents/skills/*/SKILL.md
git commit -m "docs: 修正三个 SKILL.md 的脚本路径为 .agents/skills/..."
```

---

## 任务 9：全流程回归验证

**目标：** 所有修复完成后，用本次 B 站视频一次跑通，确认页数合理、产物完整、无崩溃。

- [ ] **步骤 1：清理旧 run_dir，从头跑通**

```bash
.venv/bin/python3 .agents/skills/video-summary/scripts/process.py \
  "https://www.bilibili.com/video/BV1cNdrB4Evw/" --language zh
RD=$(ls -dt runs/【闪客】* | head -1)
.venv/bin/python3 .agents/skills/video-to-slides/scripts/process.py \
  "$RD/【闪客】你管这破玩意叫 Harness？虚拟世界的牛马套餐！.mp4" \
  --transcript "$RD/transcript.json" --run-dir "$RD" \
  --capture-mode audit --force-rebuild asr
```

- [ ] **步骤 2：校验产物质量**

```bash
.venv/bin/python3 -c "
import re,sys,glob
f=glob.glob('$RD/*整理版*.md')[0]
t=open(f).read()
pages=re.findall(r'### 第 \d+ 页', t)
print(f'页数: {len(pages)}')
assert 30 <= len(pages) <= 120, f'页数异常: {len(pages)}'
print('✅ 页数合理')
"
```
预期：页数 40-90，每页多句。

- [ ] **步骤 3：跑全量测试套件**

```bash
.venv/bin/python3 -m pytest .agents/skills/video-to-slides/scripts/videotodoc/tests/ -v
```
预期：全部 PASS。

---

## 自检

**1. 规格覆盖度：** 8 个卡点逐一对应任务——卡点①→任务8，②→任务7，③→任务5，④→任务4，⑤→任务3，⑥→任务2（_transcript_from_external 固化单位转换），⑦→任务6，⑧主卡点→任务1+2（语义合并模块+pipeline接入）。无遗漏。

**2. 占位符扫描：** 每个代码步骤含完整代码块；路径为绝对/相对精确路径；命令含预期输出。无 TODO/待定。

**3. 类型一致性：** `suggest_segments(duration_ms)` / `validate_groups(groups, n)` / `apply_groups(raw, groups)` / `normalize_raw(raw)` 在任务1定义、任务2 CLI 调用一致；`_transcript_from_external(data, language)` 在任务2定义、三处复用一致；`process_video(..., run_dir=None)` 在任务6定义、cli 调用一致；`TranscriptSegment(start_ms, end_ms, text)` 与 models.py 一致。

**4. 风险点：**
- 任务1 LLM 合并依赖 OpenAI API key（`.env` 已配），无网时自动回退机械合并（已设计降级）。
- 任务2 步骤2 pipeline 用 `_transcript_from_external` 读 `transcript_merged.json`，该文件由 `apply_merge.py` 输出 `{backend, language, segments:[{start_ms, end_ms, text}]}`，`_transcript_from_external` 的 `isinstance(data, dict)` 分支（`data.get("segments")`）可正常处理。
- 任务6 `--run-dir` 复用目录时，video-to-slides 的 cache/ 与 video-summary 产物共存，文件名不冲突（不同后缀）。
