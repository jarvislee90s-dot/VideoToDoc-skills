"""signal_stats 单元测试：纯统计提示，Constitution I 守护（不输出 archetype 决策）。

signal_stats 只返回各原型锚点信号的命中计数，**不**返回 "archetype" 键
（那会构成脚本决策，违反 Constitution I）。计数是给整理 agent 的客观提示，
类型判定权始终在 agent。
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # video-summary/

from signal_stats import signal_stats  # noqa: E402


class TestSignalStats:
    def test_no_archetype_in_output(self):
        # Constitution I 守护：脚本绝不输出 archetype 决策键
        out = signal_stats("首先点击保存，然后下一步。第三名是X。")
        assert "archetype" not in out

    def test_counts_are_int(self):
        out = signal_stats("第一步第二步第三步")
        for key, val in out.items():
            assert isinstance(val, int), f"{key}={val} 非 int"

    def test_enumeration_markers_counted(self):
        out = signal_stats("第一步第二步第三步")
        assert out["enumeration_unit"] >= 1

    def test_visual_hint_words_counted(self):
        out = signal_stats("这一页讲的是PPT的核心，下一页如图所示。")
        assert out["visual_event"] >= 1

    def test_returns_four_archetype_count_keys(self):
        # 4 个原型锚点计数键齐全（计数键≠决策键，符合 Constitution I）
        out = signal_stats("空白文本无信号")
        assert set(out) == {
            "topic_preserve",
            "enumeration_unit",
            "visual_event",
            "rescan_grid",
        }

    def test_empty_text_returns_all_zero(self):
        out = signal_stats("")
        assert all(v == 0 for v in out.values())

    def test_never_raises_on_weird_input(self):
        # 非字符串也不崩：返回全 0（Constitution I + 健壮性）
        assert all(v == 0 for v in signal_stats(None).values())  # type: ignore[arg-type]
