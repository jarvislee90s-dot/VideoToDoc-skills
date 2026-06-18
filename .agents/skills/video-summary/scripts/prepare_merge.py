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
