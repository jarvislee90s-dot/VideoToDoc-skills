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
