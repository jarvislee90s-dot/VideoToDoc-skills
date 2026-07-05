"""prepare_merge 集成测试：--archetype/--force-archetype/--visual-signals 透传 + L3 回写。

Constitution III：缺 --archetype 时 suggestion 字节等价旧 4 键 dict。
Constitution V：--visual-signals 复用 video-to-slides 的 slides.json，不重算翻页。
"""
import json

from videotodoc.prepare_merge import main  # noqa: E402


def _write_transcript(tmp_path, end_ms=690_000):
    """构造 end_ms 收尾的转录（690000ms=11.5min，匹配 suggest_segments 基准档）。"""
    n = 46
    step = end_ms // n
    segs = [
        {"start_ms": i * step, "end_ms": (i + 1) * step, "text": f"第{i}段内容文本"}
        for i in range(n)
    ]
    segs[-1]["end_ms"] = end_ms  # 精确收尾
    p = tmp_path / "transcript.json"
    p.write_text(json.dumps({"segments": segs}, ensure_ascii=False), encoding="utf-8")
    return p


def _write_slides(tmp_path, starts):
    """构造 video-to-slides 的 slides.json（SlideSet asdict 形状）。"""
    slides = [
        {
            "slide_index": i,
            "image_path": f"slide_{i}.png",
            "start_ms": st,
            "end_ms": st + 4000,
            "capture_ms": st + 3500,
            "confidence": 0.9,
            "ocr_text": None,
        }
        for i, st in enumerate(starts)
    ]
    p = tmp_path / "slides.json"
    p.write_text(json.dumps({"slides": slides, "metadata": {}}, ensure_ascii=False), encoding="utf-8")
    return p


class TestPrepareMergeArchetype:
    def test_archetype_written_to_suggestion(self, tmp_path):
        tp = _write_transcript(tmp_path)
        out = tmp_path / "merge_input.json"
        main(str(tp), out_path=str(out), archetype="rescan_grid")
        d = json.loads(out.read_text(encoding="utf-8"))
        assert d["suggestion"]["archetype"] == "rescan_grid"
        assert "strategy" in d["suggestion"]
        assert d["suggestion"]["chars_per_group_range"] == "60-220"  # ④区间

    def test_no_archetype_is_byte_identical_legacy(self, tmp_path):
        # Constitution III：缺 --archetype → auto 路径，suggestion 字节等价旧 4 键 dict
        tp = _write_transcript(tmp_path)
        out = tmp_path / "merge_input.json"
        main(str(tp), out_path=str(out))
        d = json.loads(out.read_text(encoding="utf-8"))
        assert d["suggestion"] == {
            "target_segments": 34,
            "per_group_range": "3-8",
            "max_segments": 120,
            "chars_per_group_range": "30-120",
        }

    def test_l3_rewrite_refreshes_ranges(self, tmp_path):
        # L3 回写：改 archetype 重跑，ranges 随 archetype 刷新（contract L3 回写契约）
        tp = _write_transcript(tmp_path)
        out_enum = tmp_path / "enum.json"
        main(str(tp), out_path=str(out_enum), archetype="enumeration_unit")
        d_enum = json.loads(out_enum.read_text(encoding="utf-8"))
        assert d_enum["suggestion"]["chars_per_group_range"] == "40-160"  # ②

        out_grid = tmp_path / "grid.json"
        main(str(tp), out_path=str(out_grid), archetype="rescan_grid")
        d_grid = json.loads(out_grid.read_text(encoding="utf-8"))
        assert d_grid["suggestion"]["chars_per_group_range"] == "60-220"  # ④
        assert d_enum["suggestion"]["chars_per_group_range"] != d_grid["suggestion"]["chars_per_group_range"]

    def test_force_archetype_overrides_archetype(self, tmp_path):
        # --force-archetype 绝对覆盖 --archetype（force 优先）
        tp = _write_transcript(tmp_path)
        out = tmp_path / "merge_input.json"
        main(str(tp), out_path=str(out), archetype="topic_preserve", force_archetype="rescan_grid")
        d = json.loads(out.read_text(encoding="utf-8"))
        assert d["suggestion"]["archetype"] == "rescan_grid"
        assert d["suggestion"]["chars_per_group_range"] == "60-220"

    def test_auto_with_sibling_slides_json_is_byte_identical(self, tmp_path):
        # Constitution III 集成回归门：auto 路径 + 同目录 slides.json 共存时，
        # suggestion 仍为 4 键 dict，不注入 visual_signals/warnings。
        # prepare_merge 会自动加载 slides.json，但 auto 短路不消费它——
        # 此测试守护该不变量，防未来重构把注入移到短路之前而静默破坏字节等价。
        tp = _write_transcript(tmp_path)
        _write_slides(tmp_path, starts=[0, 5000, 9000])  # 同目录 slides.json
        out = tmp_path / "merge_input.json"
        main(str(tp), out_path=str(out))  # 默认 archetype="auto"
        d = json.loads(out.read_text(encoding="utf-8"))
        assert d["suggestion"] == {
            "target_segments": 34,
            "per_group_range": "3-8",
            "max_segments": 120,
            "chars_per_group_range": "30-120",
        }
        assert "visual_signals" not in d["suggestion"]
        assert "warnings" not in d["suggestion"]


class TestPrepareMergeVisualSignals:
    def test_visual_signals_injection(self, tmp_path):
        # --visual-signals 指向 slides.json → slide_boundaries_ms 注入（Constitution V 复用）
        tp = _write_transcript(tmp_path)
        sp = _write_slides(tmp_path, starts=[0, 3000, 7000])
        out = tmp_path / "merge_input.json"
        main(str(tp), out_path=str(out), archetype="visual_event", visual_signals=str(sp))
        d = json.loads(out.read_text(encoding="utf-8"))
        # 首 slide start_ms=0 非翻页点，丢弃；剩 [3000, 7000]
        assert d["suggestion"]["visual_signals"]["slide_boundaries_ms"] == [3000, 7000]
        assert "visual_missing" not in d["suggestion"].get("warnings", [])

    def test_visual_event_without_signals_warns(self, tmp_path):
        # 原型③缺 --visual-signals（且无同目录 slides.json）→ warnings 含 visual_missing，不崩
        tp = _write_transcript(tmp_path)
        out = tmp_path / "merge_input.json"
        main(str(tp), out_path=str(out), archetype="visual_event")
        d = json.loads(out.read_text(encoding="utf-8"))
        assert "visual_missing" in d["suggestion"].get("warnings", [])

    def test_auto_detect_sibling_slides_json(self, tmp_path):
        # 缺 --visual-signals 时自动探测同目录 slides.json（复用 video-to-slides 共享 run_dir）
        tp = _write_transcript(tmp_path)
        _write_slides(tmp_path, starts=[0, 5000, 9000])  # 同目录
        out = tmp_path / "merge_input.json"
        main(str(tp), out_path=str(out), archetype="visual_event")
        d = json.loads(out.read_text(encoding="utf-8"))
        assert d["suggestion"]["visual_signals"]["slide_boundaries_ms"] == [5000, 9000]
