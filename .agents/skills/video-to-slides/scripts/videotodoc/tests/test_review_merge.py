import json

import pytest

from videotodoc.review_merge import review_groups, _parse_range, _looks_like_complement, main  # noqa: E402


class TestLooksLikeComplement:
    def test_plain_number(self):
        assert _looks_like_complement("300%到500%") is True

    def test_with_qualifier(self):
        assert _looks_like_complement("约 300%") is True
        assert _looks_like_complement("大概50亿美元") is True
        assert _looks_like_complement("超过200%") is True

    def test_plain_text(self):
        assert _looks_like_complement("最夸张的") is False


class TestReviewGroups:
    def test_group_size_exceeded(self):
        segs = [{"text": "x"} for _ in range(20)]
        groups = [{"indices": list(range(20)), "text": "".join(s["text"] for s in segs)}]
        constraints = {"per_group_range": {"min": 3, "max": 8}, "chars_per_group_range": {"min": 30, "max": 120}}
        report = review_groups(segs, groups, constraints)
        # group_size_exceeded 是 warning，不导致 pass=false
        assert report["pass"] is True
        assert any(i["type"] == "group_size_exceeded" for i in report["issues"])

    def test_chars_above_max(self):
        segs = [{"text": "这是一个很长的句子。" * 20}]
        groups = [{"indices": [0], "text": segs[0]["text"]}]
        constraints = {"per_group_range": {"min": 1, "max": 5}, "chars_per_group_range": {"min": 10, "max": 50}}
        report = review_groups(segs, groups, constraints)
        assert report["pass"] is True
        assert any(i["type"] == "chars_above_max" for i in report["issues"])

    def test_chars_below_min(self):
        segs = [{"text": "短"}, {"text": "句"}]
        groups = [{"indices": [0, 1], "text": "短句"}]
        constraints = {"per_group_range": {"min": 1, "max": 5}, "chars_per_group_range": {"min": 30, "max": 120}}
        report = review_groups(segs, groups, constraints)
        assert report["pass"] is True
        assert any(i["type"] == "chars_below_min" for i in report["issues"])

    def test_syntax_break_number(self):
        segs = [
            {"text": "价格基本都暴涨"},
            {"text": "300%到500%"},
            {"text": "最夸张的"},
        ]
        groups = [
            {"indices": [0], "text": "价格基本都暴涨"},
            {"indices": [1, 2], "text": "300%到500%，最夸张的"},
        ]
        constraints = {"per_group_range": {"min": 1, "max": 8}, "chars_per_group_range": {"min": 30, "max": 120}}
        report = review_groups(segs, groups, constraints)
        assert any(i["type"] == "syntax_break" for i in report["issues"])

    def test_syntax_break_number_with_le(self):
        # 口语转录中依存动词常带"了"，如"暴涨了"后接补语仍应被识别
        segs = [
            {"text": "价格基本都暴涨了"},
            {"text": "300%到500%"},
        ]
        groups = [
            {"indices": [0], "text": "价格基本都暴涨了"},
            {"indices": [1], "text": "300%到500%"},
        ]
        constraints = {"per_group_range": {"min": 1, "max": 8}, "chars_per_group_range": {"min": 30, "max": 120}}
        report = review_groups(segs, groups, constraints)
        assert any(i["type"] == "syntax_break" for i in report["issues"])
        assert report["pass"] is False

    def test_pass_clean(self):
        segs = [{"text": "这是一个短句"}, {"text": "这是另一个短句"}]
        groups = [{"indices": [0, 1], "text": "这是一个短句，这是另一个短句"}]
        constraints = {"per_group_range": {"min": 1, "max": 8}, "chars_per_group_range": {"min": 10, "max": 120}}
        report = review_groups(segs, groups, constraints)
        assert report["pass"] is True
        assert report["issues"] == []

    def test_high_frequency_words_no_false_positive(self):
        # "是/了/到/为" 等高频虚词后接数字，不应被误判为 syntax_break
        segs = [
            {"text": "这个事情是"},
            {"text": "2024年"},
        ]
        groups = [
            {"indices": [0], "text": "这个事情是"},
            {"indices": [1], "text": "2024年"},
        ]
        constraints = {"per_group_range": {"min": 1, "max": 8}, "chars_per_group_range": {"min": 10, "max": 120}}
        report = review_groups(segs, groups, constraints)
        assert not any(i["type"] == "syntax_break" for i in report["issues"])


class TestArchetypeSpecificRanges:
    """AC#9：review_merge 对 archetype 专属区间（如 rescan_grid 的 60-220）仍正确报告。"""

    def test_rescan_grid_chars_above_max(self):
        # rescan_grid chars_per_group_range="60-220"；一段 > 220 字 → chars_above_max
        segs = [{"text": "这是一段用于横评的较长文本。" * 20}]  # ~280 字 > 220
        groups = [{"indices": [0], "text": segs[0]["text"]}]
        constraints = {
            "per_group_range": {"min": 5, "max": 12},          # rescan_grid
            "chars_per_group_range": {"min": 60, "max": 220},   # rescan_grid
        }
        report = review_groups(segs, groups, constraints)
        assert report["pass"] is True  # warning 不致 fail
        assert any(i["type"] == "chars_above_max" for i in report["issues"])

    def test_rescan_grid_chars_below_min(self):
        # rescan_grid 区间下限 60；一段 5 字 < 60 → chars_below_min
        segs = [{"text": "短"}, {"text": "句"}]
        groups = [{"indices": [0, 1], "text": "短句"}]
        constraints = {
            "per_group_range": {"min": 5, "max": 12},
            "chars_per_group_range": {"min": 60, "max": 220},
        }
        report = review_groups(segs, groups, constraints)
        assert report["pass"] is True
        assert any(i["type"] == "chars_below_min" for i in report["issues"])


class TestParseRange:
    def test_string_range(self):
        assert _parse_range("30-120", 0, 9999) == {"min": 30, "max": 120}

    def test_dict_range(self):
        assert _parse_range({"min": 50, "max": 180}, 0, 9999) == {"min": 50, "max": 180}

    def test_default_fallback(self):
        assert _parse_range(None, 1, 999) == {"min": 1, "max": 999}

    def test_single_value_raises(self):
        with pytest.raises(ValueError, match="range 字符串格式非法"):
            _parse_range("30", 0, 9999)

    def test_too_many_parts_raises(self):
        with pytest.raises(ValueError, match="range 字符串格式非法"):
            _parse_range("30-120-180", 0, 9999)

    def test_non_numeric_raises(self):
        with pytest.raises(ValueError, match="range 数值解析失败"):
            _parse_range("abc-def", 0, 9999)


class TestMain:
    def test_main_reads_merge_input_and_writes_report(self, tmp_path):
        transcript = tmp_path / "transcript.json"
        transcript.write_text(json.dumps([{"text": "价格基本都暴涨"}, {"text": "300%到500%"}]), encoding="utf-8")

        groups = tmp_path / "merged_groups.json"
        groups.write_text(json.dumps([
            {"indices": [0], "text": "价格基本都暴涨"},
            {"indices": [1], "text": "300%到500%"},
        ]), encoding="utf-8")

        merge_input = tmp_path / "merge_input.json"
        merge_input.write_text(json.dumps({
            "suggestion": {
                "per_group_range": "1-8",
                "chars_per_group_range": "30-120",
            }
        }), encoding="utf-8")

        out = tmp_path / "report.json"
        rc = main(str(transcript), str(groups), str(out))
        assert rc == 1

        report = json.loads(out.read_text(encoding="utf-8"))
        assert report["total_groups"] == 2
        assert any(i["type"] == "syntax_break" for i in report["issues"])

    def test_main_warning_only_returns_zero(self, tmp_path):
        transcript = tmp_path / "transcript.json"
        transcript.write_text(json.dumps([{"text": "x"} for _ in range(20)]), encoding="utf-8")

        groups = tmp_path / "merged_groups.json"
        groups.write_text(json.dumps([
            {"indices": list(range(20)), "text": "".join("x" for _ in range(20))},
        ]), encoding="utf-8")

        merge_input = tmp_path / "merge_input.json"
        merge_input.write_text(json.dumps({
            "suggestion": {
                "per_group_range": "3-8",
                "chars_per_group_range": "30-120",
            }
        }), encoding="utf-8")

        out = tmp_path / "report.json"
        rc = main(str(transcript), str(groups), str(out))
        assert rc == 0

        report = json.loads(out.read_text(encoding="utf-8"))
        assert any(i["type"] == "group_size_exceeded" for i in report["issues"])
