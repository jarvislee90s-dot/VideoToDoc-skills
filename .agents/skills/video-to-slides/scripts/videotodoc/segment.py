"""时长密度函数 + 分段草案启发式 + confirmed 格式校验。"""
from __future__ import annotations


def capture_interval_for_duration(duration_sec: float) -> int:
    """根据视频时长返回初始截图间隔（秒）。

    duration ≤ 5min  → 15s
    duration ≤ 15min → 20s
    duration ≤ 30min → 30s
    duration > 30min → 40s
    """
    if duration_sec <= 300:
        return 15
    if duration_sec <= 900:
        return 20
    if duration_sec <= 1800:
        return 30
    return 40
