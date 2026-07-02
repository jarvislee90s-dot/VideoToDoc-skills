"""转录碎段语义合并的共享逻辑（不调大模型）。

agent 负责语义分组与文字整理，脚本只算目标段数建议、校验 index 结构、
重算时间戳。校验只查 index，不查 text。

suggest_segments 委托 strategies.resolve_suggestion：auto/未知原型字节等价旧逻辑
（Constitution III），已知原型按时长档 target/max + 原型策略 ranges 组合。
"""
from __future__ import annotations

from .strategies import resolve_suggestion  # noqa: E402  （strategies 不反向依赖 __init__，无循环导入）


def _seconds_to_ms(seconds: float) -> int:
    return max(0, int(round(float(seconds) * 1000)))


def suggest_segments(
    duration_ms: int,
    archetype: str = "auto",
    visual_signals: dict | None = None,
) -> dict:
    """按视频时长 + 结构形态原型决定分段建议。段数为软目标，同话题完整优先。

    - ``suggest_segments(duration_ms)``：archetype 缺省 ``"auto"``，返回值逐字节等价改动前
      （Constitution III 非协商回归门，旧 4 键 dict，无 archetype/strategy 键）。
    - ``suggest_segments(duration_ms, archetype=<已知原型>)``：target/max 取自时长档，
      per_group/chars 取自原型策略，附 ``archetype`` + ``strategy``。
    - visual_signals 为原型③预留，当前透传（③实际消费在后续任务）。
    """
    return resolve_suggestion(duration_ms, archetype, visual_signals)


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
