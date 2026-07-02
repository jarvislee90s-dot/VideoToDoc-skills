#!/usr/bin/env python3
"""准备语义合并：读 transcript.json → 输出 merge_input.json（目标段数建议 + 带 index 短句清单）。
不调大模型。供 agent 读取后做语义分组。

Constitution I：脚本只算约束不决策——archetype 由用户/agent 给（L1 先验）或 agent
全文判定后回写（L3），signal_stats 仅作客观提示。脚本本身不判定视频类型。
Constitution III：缺 --archetype 时 archetype="auto"，suggestion 字节等价旧 4 键 dict。
Constitution V：原型③的翻页边界复用 video-to-slides 已产出的 slides.json，不重算。
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_shared"))
from transcript_merge import suggest_segments, normalize_raw  # noqa: E402

# video-summary/ 根（signal_stats 提示用，懒导入，失败静默）
_VIDEO_SUMMARY_DIR = str(Path(__file__).resolve().parents[1])


def _load_visual_signals(path: str | None) -> dict | None:
    """从 slides.json 提取 slide_boundaries_ms（复用 video-to-slides 产物，Constitution V）。

    slides.json 形状：``{"slides": [{start_ms, end_ms, ...}], "metadata": {}}``（SlideSet asdict）。
    取每张 slide 的 start_ms 作为翻页边界点；丢弃 0（首帧非"翻页点"）。
    缺失/不可解析/无有效边界返回 None（原型③据此降级 warning，不崩）。
    """
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    slides = data.get("slides") if isinstance(data, dict) else data
    if not isinstance(slides, list):
        return None
    # 首 slide 的 start_ms 是视频开头而非翻页点，按位置丢弃（slides[0]）；
    # 其余 slide 的 start_ms 即翻页边界。按位置丢弃比 ">0" 更鲁棒：
    # 即使 slide[0].start_ms 非 0（片头/logo）也不会被误当翻页点。
    boundaries: list[int] = []
    for s in slides[1:]:
        if isinstance(s, dict) and isinstance(s.get("start_ms"), (int, float)):
            boundaries.append(int(s["start_ms"]))
    if not boundaries:
        return None
    return {"slide_boundaries_ms": boundaries}


def _print_signal_hint(segs: list[dict]) -> None:
    """打印 signal_stats 提示供 agent 做 L3 类型判定（Constitution I：只提示不决策）。

    仅 archetype="auto"（用户未声明类型）时调用。失败静默——提示非必需，不影响主流程。
    """
    try:
        sys.path.insert(0, _VIDEO_SUMMARY_DIR)
        from signal_stats import signal_stats  # noqa: WPS433
    except Exception:
        return
    text = " ".join(s.get("text", "") for s in segs)
    stats = signal_stats(text)
    hint = "，".join(f"{k}={v}" for k, v in stats.items())
    print(f"     信号提示（非决策，供 agent 判定结构形态）：{hint}")


def main(
    transcript_path: str,
    out_path: str | None = None,
    archetype: str = "auto",
    force_archetype: str | None = None,
    visual_signals: str | None = None,
    tid: int | None = None,
) -> None:
    data = json.loads(Path(transcript_path).read_text(encoding="utf-8"))
    raw = data if isinstance(data, list) else data.get("segments", [])
    segs = normalize_raw(raw)
    for i, s in enumerate(segs):
        s["index"] = i
    duration_ms = segs[-1]["end_ms"] if segs else 0

    # archetype 解析：--force-archetype 绝对覆盖（跳过 L3），否则用 --archetype（L1 先验），缺省 auto
    resolved = force_archetype or archetype

    # 视觉信号：--visual-signals 优先；否则自动探测同目录 slides.json（复用 video-to-slides 共享 run_dir）
    vs_path = visual_signals
    if vs_path is None:
        auto_slides = Path(transcript_path).parent / "slides.json"
        if auto_slides.exists():
            vs_path = str(auto_slides)
    visual_signals_dict = _load_visual_signals(vs_path)

    suggestion = suggest_segments(
        duration_ms, archetype=resolved, visual_signals=visual_signals_dict
    )

    out = {
        "total_segments": len(segs),
        "duration_ms": duration_ms,
        "suggestion": suggestion,
        "segments": segs,
    }
    out_path = out_path or str(Path(transcript_path).parent / "merge_input.json")
    Path(out_path).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  📝 合并输入清单：{out_path}")
    print(f"     共 {len(segs)} 碎句，时长 {duration_ms/1000:.0f}s，建议目标约 {suggestion.get('target_segments')} 段")
    if resolved != "auto":
        source = "force（跳过 L3）" if force_archetype else "L1 先验（agent 可 L3 复核）"
        print(f"     结构形态原型：{resolved}（{source}）")
    else:
        _print_signal_hint(segs)  # 用户未声明类型 → 给 agent 客观提示做 L3
    if tid is not None:
        print(f"     B站分区 tid={tid}（仅提示，类型判定归 agent）")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="准备语义合并输入清单（不调大模型）")
    ap.add_argument("transcript", help="transcript.json 路径")
    ap.add_argument("-o", "--output", default=None, help="输出 merge_input.json 路径")
    ap.add_argument(
        "--archetype",
        default="auto",
        choices=["auto", "topic_preserve", "enumeration_unit", "visual_event", "rescan_grid"],
        help="L1 加权先验：用户声明的结构形态原型（agent 可 L3 全文复核覆盖）",
    )
    ap.add_argument(
        "--force-archetype",
        default=None,
        choices=["topic_preserve", "enumeration_unit", "visual_event", "rescan_grid"],
        help="绝对覆盖原型，跳过 L3（用户确信时用）",
    )
    ap.add_argument(
        "--visual-signals",
        default=None,
        help="slides.json 路径（原型③翻页边界；缺省自动探测同目录 slides.json）",
    )
    ap.add_argument("--tid", default=None, type=int, help="B站分区 tid，仅提示用")
    a = ap.parse_args()
    main(
        a.transcript,
        a.output,
        archetype=a.archetype,
        force_archetype=a.force_archetype,
        visual_signals=a.visual_signals,
        tid=a.tid,
    )
