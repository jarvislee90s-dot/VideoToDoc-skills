"""strategies.py 单元测试：4 原型注册表 + get_strategy。

Constitution IV：注册表为纯数据；Constitution I：此处不含任何决策逻辑。
"""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "_shared"))

from transcript_merge.strategies import (  # noqa: E402
    STRATEGY_REGISTRY,
    get_strategy,
    resolve_suggestion,
)


class TestStrategyRegistry:
    def test_registry_has_4_archetypes(self):
        assert set(STRATEGY_REGISTRY) == {
            "topic_preserve",
            "enumeration_unit",
            "visual_event",
            "rescan_grid",
        }

    def test_visual_event_requires_visual(self):
        assert get_strategy("visual_event").visual_required == "required"

    def test_get_unknown_raises(self):
        with pytest.raises(KeyError):
            get_strategy("nope")

    def test_auto_is_not_a_registry_key(self):
        # "auto" 由 suggest_segments/resolve_suggestion 特判回退时长档，
        # 不在注册表里；get_strategy("auto") 应抛 KeyError。
        with pytest.raises(KeyError):
            get_strategy("auto")

    def test_every_strategy_has_all_fields(self):
        required = {
            "principle",
            "per_group_range",
            "chars_per_group_range",
            "paragraph_tendency",
            "anchors",
            "visual_required",
        }
        for key, strat in STRATEGY_REGISTRY.items():
            missing = required - set(strat.__dict__)
            assert not missing, f"{key} 缺字段 {missing}"
            assert strat.anchors, f"{key} anchors 不能为空"

    def test_ranges_are_dash_format(self):
        for key, strat in STRATEGY_REGISTRY.items():
            lo, hi = strat.per_group_range.split("-")
            clo, chi = strat.chars_per_group_range.split("-")
            assert int(lo) < int(hi), f"{key} per_group_range 非法"
            assert int(clo) < int(chi), f"{key} chars_per_group_range 非法"


class TestResolveSuggestionVisualSignals:
    """US2：原型③ visual_signals 通道 + 缺信号降级不崩（Constitution I/V）。"""

    def test_visual_event_without_signals_warns(self):
        s = resolve_suggestion(690_000, archetype="visual_event", visual_signals=None)
        assert "visual_missing" in s.get("warnings", [])
        assert s["strategy"]["visual_required"] == "required"
        # 缺信号时不应注入空壳 visual_signals
        assert "visual_signals" not in s

    def test_visual_event_with_signals(self):
        s = resolve_suggestion(
            690_000,
            archetype="visual_event",
            visual_signals={"slide_boundaries_ms": [1000, 5000]},
        )
        assert s["visual_signals"]["slide_boundaries_ms"] == [1000, 5000]
        assert "visual_missing" not in s.get("warnings", [])

    def test_visual_event_with_empty_boundaries_warns(self):
        # 给了 visual_signals 但 slide_boundaries_ms 为空 → 视同缺失，降级 warning
        s = resolve_suggestion(
            690_000,
            archetype="visual_event",
            visual_signals={"slide_boundaries_ms": []},
        )
        assert "visual_missing" in s.get("warnings", [])

    def test_non_visual_archetype_ignores_visual_signals(self):
        # 非③原型不消费 visual_signals：不注入 visual_signals / warnings
        s = resolve_suggestion(
            690_000,
            archetype="topic_preserve",
            visual_signals={"slide_boundaries_ms": [1000]},
        )
        assert "visual_signals" not in s
        assert "warnings" not in s

    def test_auto_path_unaffected_by_visual_signals(self):
        # Constitution III：auto 路径字节等价，visual_signals 不改变 4 键 dict
        s = resolve_suggestion(
            690_000,
            archetype="auto",
            visual_signals={"slide_boundaries_ms": [1000]},
        )
        assert s == {
            "target_segments": 34,
            "per_group_range": "3-8",
            "max_segments": 120,
            "chars_per_group_range": "30-120",
        }

    def test_visual_event_strategy_anchors_contain_slide_change(self):
        # AC#6：原型③的 strategy.anchors 必须含 "slide_change"（正向断言，
        # 对照 rescan_grid 的负向断言）
        s = resolve_suggestion(690_000, archetype="visual_event")
        assert "slide_change" in s["strategy"]["anchors"]
        assert "scene_change" in s["strategy"]["anchors"]
        assert s["strategy"]["visual_required"] == "required"
