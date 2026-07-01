from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "_shared"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from review_merge import review_groups  # noqa: E402


class TestReviewGroups:
    def test_group_size_exceeded(self):
        segs = [{"text": "x"} for _ in range(20)]
        groups = [{"indices": list(range(20)), "text": "".join(s["text"] for s in segs)}]
        constraints = {"per_group_range": {"min": 3, "max": 8}, "chars_per_group_range": {"min": 30, "max": 120}}
        report = review_groups(segs, groups, constraints)
        assert report["pass"] is False
        assert any(i["type"] == "group_size_exceeded" for i in report["issues"])

    def test_chars_above_max(self):
        segs = [{"text": "这是一个很长的句子。" * 20}]
        groups = [{"indices": [0], "text": segs[0]["text"]}]
        constraints = {"per_group_range": {"min": 1, "max": 5}, "chars_per_group_range": {"min": 10, "max": 50}}
        report = review_groups(segs, groups, constraints)
        assert any(i["type"] == "chars_above_max" for i in report["issues"])

    def test_chars_below_min(self):
        segs = [{"text": "短"}]
        groups = [{"indices": [0], "text": "短"}]
        constraints = {"per_group_range": {"min": 1, "max": 5}, "chars_per_group_range": {"min": 30, "max": 120}}
        report = review_groups(segs, groups, constraints)
        assert any(i["type"] == "chars_below_min" for i in report["issues"])

    def test_syntax_break_number(self):
        segs = [
            {"text": "价格基本都暴涨了"},
            {"text": "300%到500%"},
            {"text": "最夸张的"},
        ]
        groups = [
            {"indices": [0], "text": "价格基本都暴涨了"},
            {"indices": [1, 2], "text": "300%到500%，最夸张的"},
        ]
        constraints = {"per_group_range": {"min": 1, "max": 8}, "chars_per_group_range": {"min": 30, "max": 120}}
        report = review_groups(segs, groups, constraints)
        assert any(i["type"] == "syntax_break" for i in report["issues"])

    def test_pass_clean(self):
        segs = [{"text": "短句一"}, {"text": "短句二"}]
        groups = [{"indices": [0, 1], "text": "短句一，短句二"}]
        constraints = {"per_group_range": {"min": 1, "max": 8}, "chars_per_group_range": {"min": 10, "max": 120}}
        report = review_groups(segs, groups, constraints)
        assert report["pass"] is True
        assert report["issues"] == []
