from transcript_merge import suggest_segments, validate_groups


class TestSuggestSegments:
    def test_short_11min(self):
        s = suggest_segments(690_000)  # 11.5min
        assert s["target_segments"] == 34
        assert s["per_group_range"] == "3-8"
        assert s["max_segments"] == 120
        assert s["chars_per_group_range"] == "30-120"

    def test_1h(self):
        s = suggest_segments(3_600_000)
        assert s["target_segments"] == 90
        assert s["max_segments"] == 120
        assert s["chars_per_group_range"] == "80-270"

    def test_2h(self):
        s = suggest_segments(7_200_000)
        assert s["max_segments"] == 240
        assert s["target_segments"] == 144
        assert s["chars_per_group_range"] == "120-400"

    def test_tiny_video_floor(self):
        s = suggest_segments(60_000)  # 1min
        assert s["target_segments"] >= 8
        assert s["chars_per_group_range"] == "30-120"

    def test_legacy_signature_unchanged(self):
        # Constitution III 非协商回归门：旧签名逐字节等价（auto 路径不新增任何键）
        assert suggest_segments(690_000) == {
            "target_segments": 34,
            "per_group_range": "3-8",
            "max_segments": 120,
            "chars_per_group_range": "30-120",
        }
        assert suggest_segments(3_600_000)["target_segments"] == 90
        assert suggest_segments(7_200_000) == {
            "target_segments": 144,
            "per_group_range": "12-25",
            "max_segments": 240,
            "chars_per_group_range": "120-400",
        }

    def test_auto_path_has_no_archetype_field(self):
        # auto 路径字节等价旧返回 → 不应冒出 archetype/strategy 键
        s = suggest_segments(690_000)
        assert "archetype" not in s
        assert "strategy" not in s

    def test_archetype_overrides_ranges(self):
        s = suggest_segments(690_000, archetype="rescan_grid")
        assert s["chars_per_group_range"] == "60-220"   # 来自原型④而非时长档 30-120
        assert s["per_group_range"] == "5-12"           # 来自原型④
        assert s["target_segments"] == 34               # target 仍取自时长档
        assert s["max_segments"] == 120                # max 仍取自时长档
        assert s["archetype"] == "rescan_grid"
        assert s["strategy"]["principle"]               # 原则非空
        assert "slide_change" not in s["strategy"]["anchors"]  # ④ 锚点不含视觉


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
