"""结构形态原型分段策略注册表（纯数据，无决策）。

Constitution I：本模块不含任何分段/分类决策——只提供原型策略区间与原则提示。
Constitution IV：新增一种结构形态只需在 STRATEGY_REGISTRY 加一条。
Constitution V：原型③的视觉信号消费在 resolve_suggestion（见 __init__.py），
此处只声明 visual_required，不实现检测。

原型由"段落边界触发器"分类（见 spec 设计原则），4 个两两策略不同：
  ① topic_preserve    话题/事件转折，线性切，宁少切勿多（粗）
  ② enumeration_unit  显式枚举标记，一单元一段（细）
  ③ visual_event      外部视觉事件（PPT 翻页）硬边界优先（需图）
  ④ rescan_grid       不能线性切，先扫全文建网格再分（重组）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple


@dataclass(frozen=True)
class SegmentStrategy:
    """一个结构形态原型的分段策略（纯数据）。"""
    principle: str                       # 边界触发器原则（给 agent 看）
    per_group_range: str                  # 每段短句数区间，如 "6-15"
    chars_per_group_range: str            # 每段字数区间，如 "80-320"
    paragraph_tendency: str               # 分段倾向标签
    anchors: Tuple[str, ...] = ()         # 锚点类型
    visual_required: str = "none"         # none|optional|required|optional_if_no_diarization


# 4 原型策略。新增原型只在此加一条（Constitution IV）。
STRATEGY_REGISTRY: dict[str, SegmentStrategy] = {
    "topic_preserve": SegmentStrategy(
        principle="边界=话题/事件/时间转折；线性扫到即切；宁少切勿多切",
        per_group_range="6-15",
        chars_per_group_range="80-320",
        paragraph_tendency="preserve_natural_paragraphs_coarse",
        anchors=("topic_transition_words", "time_markers", "qa_transition"),
        visual_required="none",
    ),
    "enumeration_unit": SegmentStrategy(
        principle="边界=显式枚举标记（步骤词/序数词/item 词）；一个枚举单元一段",
        per_group_range="3-8",
        chars_per_group_range="40-160",
        paragraph_tendency="one_marker_unit_per_segment",
        anchors=("step_words", "ordinal_words", "item_markers"),
        visual_required="none",
    ),
    "visual_event": SegmentStrategy(
        principle="边界=外部视觉事件(PPT翻页/场景切换)；硬边界优先，事件区间内再按语义子话题细分",
        per_group_range="4-12",
        chars_per_group_range="50-240",
        paragraph_tendency="visual_boundary_then_subtopic",
        anchors=("slide_change", "scene_change", "heading_text"),
        visual_required="required",
    ),
    "rescan_grid": SegmentStrategy(
        principle="不能线性切；先扫全文建 item×维度 网格再分",
        per_group_range="5-12",
        chars_per_group_range="60-220",
        paragraph_tendency="scan_then_grid_item_dimension",
        anchors=("item_markers", "dimension_words", "comparison_markers"),
        visual_required="none",
    ),
}


def get_strategy(archetype: str) -> SegmentStrategy:
    """取原型策略。未知 key 抛 KeyError（auto 不在此，由调用方特判回退时长档）。"""
    return STRATEGY_REGISTRY[archetype]


def _time_tier(duration_ms: int) -> dict:
    """时长四档建议：返回旧 suggest_segments 的 4 键 dict。

    Constitution III：auto 路径字节等价旧返回——本函数即旧逻辑本身，
    auto/未知原型直接返回它，保证逐字节一致。
    """
    duration_sec = duration_ms / 1000
    duration_min = duration_sec / 60
    if duration_min <= 15:
        target = max(8, int(duration_sec / 20))
        per_group = "3-8"
        chars_range = "30-120"
    elif duration_min <= 30:
        target = max(12, int(duration_sec / 30))
        per_group = "5-12"
        chars_range = "50-180"
    elif duration_min <= 60:
        target = max(20, int(duration_sec / 40))
        per_group = "8-18"
        chars_range = "80-270"
    else:
        target = max(30, int(duration_sec / 50))
        per_group = "12-25"
        chars_range = "120-400"
    max_seg = int(duration_min * 2) if duration_min > 60 else 120
    target = min(target, max_seg)
    return {
        "target_segments": target,
        "per_group_range": per_group,
        "max_segments": max_seg,
        "chars_per_group_range": chars_range,
    }


def _extract_boundaries(visual_signals: dict | None) -> list:
    """从 visual_signals 取 slide_boundaries_ms；缺失/空/非列表返回 []。

    非决策（Constitution I）：只做取值与类型归一，不判定原型。
    """
    if not isinstance(visual_signals, dict):
        return []
    boundaries = visual_signals.get("slide_boundaries_ms")
    if not isinstance(boundaries, list) or not boundaries:
        return []
    # 类型守卫：跳过非数值元素，避免 int() 崩溃（与 _load_visual_signals 的防御性对称）
    return [int(b) for b in boundaries if isinstance(b, (int, float))]


def resolve_suggestion(
    duration_ms: int,
    archetype: str = "auto",
    visual_signals: dict | None = None,
) -> dict:
    """组合时长档 target/max + 原型策略 ranges。

    - archetype="auto" 或未知 → 返回 _time_tier（4 键，字节等价旧返回，Constitution III）。
    - 已知原型 → target/max 取自时长档，per_group/chars 取自原型策略，附 archetype + strategy。
    - 原型③（visual_required=="required"）消费 visual_signals.slide_boundaries_ms：
      有边界则注入 ``visual_signals``；缺/空则降级 ``warnings=["visual_missing"]`` 不崩。
      其它原型不消费 visual_signals（spec：仅③用）。

    本函数不含分段/分类决策（Constitution I）——只做区间组合与取值注入。
    """
    tier = _time_tier(duration_ms)
    if archetype not in STRATEGY_REGISTRY:
        # 含 "auto" 与任何未知值 → 回退时长档（字节等价旧返回）
        return tier
    strat = STRATEGY_REGISTRY[archetype]
    suggestion = {
        "target_segments": tier["target_segments"],          # 取自时长档
        "per_group_range": strat.per_group_range,             # 取自原型
        "chars_per_group_range": strat.chars_per_group_range,
        "max_segments": tier["max_segments"],                 # 取自时长档
        "archetype": archetype,
        "strategy": {
            "principle": strat.principle,
            "paragraph_tendency": strat.paragraph_tendency,
            "anchors": list(strat.anchors),
            "visual_required": strat.visual_required,
        },
    }
    # 仅原型③（visual_required=="required"）消费视觉信号；缺则降级 warning 不崩
    if strat.visual_required == "required":
        boundaries = _extract_boundaries(visual_signals)
        if boundaries:
            suggestion["visual_signals"] = {"slide_boundaries_ms": boundaries}
        else:
            suggestion["warnings"] = ["visual_missing"]
    return suggestion

