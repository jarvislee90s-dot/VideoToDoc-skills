from transcript_merge import suggest_segments, validate_groups


class TestSuggestSegments:
    def test_short_11min(self):
        s = suggest_segments(690_000)  # 11.5min
        assert s["target_segments"] == 34
        assert s["per_group_range"] == "3-8"
        assert s["max_segments"] == 120

    def test_1h(self):
        s = suggest_segments(3_600_000)
        assert s["target_segments"] == 90
        assert s["max_segments"] == 120

    def test_2h_cap(self):
        s = suggest_segments(7_200_000)
        assert s["max_segments"] == 240  # 120min*2
        assert s["target_segments"] == 144  # 7200/50

    def test_tiny_video_floor(self):
        s = suggest_segments(60_000)  # 1min
        assert s["target_segments"] >= 8


class TestValidateGroups:
    def test_valid_cover(self):
        groups = [{"indices": [0, 1, 2]}, {"indices": [3, 4]}]
        ok, _ = validate_groups(groups, 5)
        assert ok is True

    def test_missing_index(self):
        groups = [{"indices": [0, 1]}, {"indices": [3, 4]}]  # 缺2
        ok, detail = validate_groups(groups, 5)
        assert ok is False
        assert "2" in detail

    def test_non_contiguous_in_group(self):
        groups = [{"indices": [0, 2]}, {"indices": [1, 3, 4]}]  # 第0组跳号
        ok, detail = validate_groups(groups, 5)
        assert ok is False
        assert "不连续" in detail

    def test_duplicate(self):
        groups = [{"indices": [0, 1, 1]}, {"indices": [2, 3, 4]}]  # 1重复
        ok, detail = validate_groups(groups, 5)
        assert ok is False

    def test_text_never_checked(self):
        # text 随便写甚至缺失都不影响校验（只查 index）
        groups = [{"indices": [0, 1], "text": ""}, {"indices": [2, 3, 4], "text": "完全无关的错字"}]
        ok, _ = validate_groups(groups, 5)
        assert ok is True
