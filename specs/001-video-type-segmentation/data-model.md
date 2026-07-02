# Data Model：视频类型→转录分段策略

## 核心数据结构

### `SegmentStrategy`（dataclass，strategies.py）

```python
@dataclass(frozen=True)
class SegmentStrategy:
    principle: str                 # 该原型的边界触发器原则（给 agent 看）
    per_group_range: str           # "6-15"
    chars_per_group_range: str     # "80-320"
    paragraph_tendency: str        # 倾向标签，如 "preserve_natural_paragraphs_coarse"
    anchors: tuple[str, ...]       # 锚点类型，如 ("topic_transition_words","time_markers")
    visual_required: str           # "none"|"optional"|"required"|"optional_if_no_diarization"
```

### `STRATEGY_REGISTRY: dict[str, SegmentStrategy]`

4 条 key：`topic_preserve` / `enumeration_unit` / `visual_event` / `rescan_grid`。
值见 spec「关键设计决策 2」表格。

### `suggestion` dict（`suggest_segments` 返回 + merge_input.json.suggestion）

```jsonc
{
  "target_segments": 90,          // 取自时长档（≤60min: max(20, sec/40)）
  "per_group_range": "5-12",      // 取自原型策略
  "chars_per_group_range": "60-220",
  "max_segments": 120,            // 取自时长档
  "archetype": "rescan_grid",     // 新增；"auto" 时为 "auto"
  "strategy": {                   // 新增；取自原型策略；archetype=auto 时为 {"principle":"auto",...} 或省略
    "principle": "不能线性切；先扫全文建 item×维度 网格再分",
    "paragraph_tendency": "scan_then_grid_item_dimension",
    "anchors": ["item_markers","dimension_words","comparison_markers"],
    "visual_required": "none"
  },
  "visual_signals": {             // 新增，可选；仅原型③用
    "slide_boundaries_ms": [1000, 5230, 9800]
  },
  "warnings": ["visual_missing"]  // 新增，可选；原型③缺 visual_signals 时
}
```

### `signal_stats` 输出（signal_stats.py，非决策）

```jsonc
{
  "topic_preserve": 4,        // 命中 topic_transition/time_markers 计数
  "enumeration_unit": 7,     // 命中 step_words/ordinal_words 计数
  "visual_event": 2,         // 命中 "这一页/下一页/如图" 计数
  "rescan_grid": 3           // 命中 item_markers/dimension_words 计数
  // 注意：无 "archetype" 键 —— Constitution I 守护
}
```

## 实体关系

```
video_type(用户/agent 声明) ──► archetype ∈ {4 原型, auto}
                                    │
                     STRATEGY_REGISTRY[archetype] ──► SegmentStrategy
                                    │
duration_ms ──────────────► resolve_suggestion ──► suggestion{target/ranges/strategy/visual/warnings}
archetype ──────────────┘           │
visual_signals ──────────┘           ▼
                          merge_input.json.suggestion ──► 整理 agent / review agent / review_merge.py(客观检查)
```

## 验证规则

- `get_strategy(archetype)`：archetype 必须在 `STRATEGY_REGISTRY`，否则抛 `KeyError`（`"auto"` 不在注册表，由 `resolve_suggestion` 特判回退，不经 `get_strategy`）。
- `auto` 路径（`archetype="auto"`/缺省/未知）：`suggestion` 字节等价旧 4 键 dict（`target_segments`/`per_group_range`/`max_segments`/`chars_per_group_range`），**无** `archetype`/`strategy`/`visual_signals`/`warnings` 键（Constitution III 逐字节等价）。
- 已知原型路径：返回 4 个时长档 target/max + 原型策略 ranges + `archetype` + `strategy`。
- `visual_event` + `visual_signals is None` → `warnings` 含 `"visual_missing"`，不抛异常。
- `signal_stats` 输出 dict 的 value 全为 `int`，无 `archetype` 键。
