# Contracts

## `suggest_segments` 接口契约

```python
def suggest_segments(
    duration_ms: int,
    archetype: str = "auto",           # topic_preserve|enumeration_unit|visual_event|rescan_grid|"auto"
    visual_signals: dict | None = None, # {"slide_boundaries_ms": list[int], ...} 原型③用
) -> dict
```

**向后兼容（非协商）**：`suggest_segments(duration_ms)`（旧签名）返回值逐字节等价于改动前。
回归基准（已用本机 .venv 核实）：
- `690000` → `{"target_segments":34,"per_group_range":"3-8","max_segments":120,"chars_per_group_range":"30-120"}`
- `3600000` → `target_segments=90, max_segments=120, chars_per_group_range="80-270"`
- `7200000` → `{"target_segments":144,"per_group_range":"12-25","max_segments":240,"chars_per_group_range":"120-400"}`

已知原型时返回值新增字段：`archetype`、`strategy`（+ 后续原型③的 `visual_signals`/`warnings`）。
`archetype="auto"`（或缺省/未知）时返回**字节等价旧 4 键 dict**，无 `archetype`/`strategy` 等新增键（Constitution III 非协商）。

**输入约束**：`duration_ms >= 0`；`archetype` 合法或 `auto`；`visual_signals` 仅原型③消费。

**输出约束**：`target_segments`、`max_segments` 始终取自时长档（与旧逻辑同公式）；`per_group_range`、`chars_per_group_range`、`strategy` 取自原型策略。

---

## `merge_input.json` 契约（prepare_merge.py 输出）

```jsonc
{
  "total_segments": <int>,         // 不变
  "duration_ms": <int>,           // 不变
  "suggestion": {                 // 见 data-model.md
    "target_segments", "per_group_range", "chars_per_group_range",
    "max_segments", "archetype", "strategy", "visual_signals"?, "warnings"?
  },
  "segments": [ {index, start_ms, end_ms, text} ]  // 不变
}
```

**消费者**：
- 整理 agent：读 `suggestion.strategy.principle`/`anchors` 调整分组倾向；区域级混合时按区域套对应原型。
- review agent：同上，复核。
- `review_merge.py`：只读 `suggestion.per_group_range`/`chars_per_group_range` 做客观检查，**逻辑不变**，新字段透明。

**L3 回写契约**：agent 做 L3 全文判定后若 archetype 变化，重跑 `prepare_merge.py --archetype <L3>` 刷新 suggestion（ranges 随 archetype 一致），再合并。否则 review 阶段用旧区间误报。

---

## `signal_stats` 契约（signal_stats.py）

```python
def signal_stats(transcript_text: str) -> dict[str, int]
```

**非决策（Constitution I）**：返回值**不含** `archetype` 键，仅 `{原型: 命中计数}`。可被 agent 忽略。失败返回全 0 不抛。

---

## `prepare_merge.py` CLI 契约

```
prepare_merge.py <transcript.json>
  [-o <out>]
  [--archetype <topic_preserve|enumeration_unit|visual_event|rescan_grid>]   # 加权先验（L1）
  [--force-archetype <id>]    # 绝对覆盖，跳过 L3
  [--visual-signals <slides.json path>]
  [--tid <int>]               # B站分区 tid，仅提示用
```

缺 `--archetype` 时 `archetype="auto"`（回退时长档），并可选打印 `signal_stats` 提示供 agent 自行判断。
`--visual-signals` 指向 `slides.json`；`slides.json` 缺失时原型③降级 warning 不崩。
