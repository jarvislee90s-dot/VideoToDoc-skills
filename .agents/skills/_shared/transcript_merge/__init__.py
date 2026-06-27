"""转录碎段语义合并的共享逻辑（不调大模型）。

agent 负责语义分组与文字整理，脚本只算目标段数建议、校验 index 结构、
重算时间戳。校验只查 index，不查 text。
"""
from __future__ import annotations


def _seconds_to_ms(seconds: float) -> int:
    return max(0, int(round(float(seconds) * 1000)))


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
            sms = _seconds_to_ms(s.get("start", 0))
            ems = _seconds_to_ms(s.get("end", 0))
        out.append({"start_ms": sms, "end_ms": ems, "text": s.get("text", "")})
    return out
