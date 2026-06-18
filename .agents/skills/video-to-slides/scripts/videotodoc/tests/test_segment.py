from videotodoc.segment import capture_interval_for_duration


class TestCaptureInterval:
    def test_short_video_5min(self):
        assert capture_interval_for_duration(300) == 15

    def test_15min_video(self):
        assert capture_interval_for_duration(900) == 20

    def test_30min_video(self):
        assert capture_interval_for_duration(1800) == 30

    def test_long_video_over_30min(self):
        assert capture_interval_for_duration(3600) == 40

    def test_boundary_5min(self):
        assert capture_interval_for_duration(301) == 20

    def test_boundary_15min(self):
        assert capture_interval_for_duration(901) == 30

    def test_boundary_30min(self):
        assert capture_interval_for_duration(1801) == 40


from videotodoc.segment import generate_pending_segments, validate_confirmed_segments
from videotodoc.models import Slide, SlideSet, TranscriptSegment, Transcript


class TestGeneratePendingSegments:
    def _make_candidates(self, times_ms: list[int]) -> SlideSet:
        return SlideSet(slides=[
            Slide(slide_index=i + 1, image_path=f"img{i}.png", start_ms=t, end_ms=t + 1000,
                  capture_ms=t, confidence=0.8, hash="0" * 16, edge_density=0.5)
            for i, t in enumerate(times_ms)
        ])

    def _make_transcript(self, segments: list[tuple[int, int, str]]) -> Transcript:
        return Transcript(
            backend="test", language="zh",
            segments=[TranscriptSegment(start_ms=s, end_ms=e, text=t) for s, e, t in segments],
        )

    def test_basic_segmentation(self):
        candidates = self._make_candidates([0, 30000, 60000])
        transcript = self._make_transcript([
            (0, 30000, "大家好这是开篇介绍。"),
            (30000, 60000, "接下来讲选购要点。"),
            (60000, 90000, "最后是产品推荐。"),
        ])
        result = generate_pending_segments(candidates, transcript, duration_sec=90)
        # 短文本片段在 max_segment_chars 内自然合并
        assert len(result["segments"]) >= 1
        assert result["capture_interval_sec"] == 15
        assert all("suggested_action" in s for s in result["segments"])

    def test_step_words_force_keep(self):
        candidates = self._make_candidates([0, 15000, 30000])
        transcript = self._make_transcript([
            (0, 15000, "第一步打开设置。"),
            (15000, 30000, "然后点击导出。"),
            (30000, 45000, "接下来保存文件。"),
        ])
        result = generate_pending_segments(candidates, transcript, duration_sec=45)
        step_segments = [s for s in result["segments"] if "第一步" in s["transcript_preview"]
                         or "然后" in s["transcript_preview"] or "接下来" in s["transcript_preview"]]
        # 含步骤词的段不应被标记为 merge
        for s in step_segments:
            assert s["suggested_action"] == "keep"

    def test_long_segment_split(self):
        long_text = "这是一个很长的讲解。" * 100  # > 400 字
        candidates = self._make_candidates([0])
        transcript = self._make_transcript([(0, 120000, long_text)])
        result = generate_pending_segments(candidates, transcript, duration_sec=120)
        split_segments = [s for s in result["segments"] if s["suggested_action"] == "split"]
        assert len(split_segments) >= 1


class TestValidateConfirmedSegments:
    def test_valid_confirmed(self):
        pending = {
            "segments": [
                {"id": "s01", "start_ms": 0, "end_ms": 30000, "label": "开篇",
                 "suggested_action": "keep", "candidate_slide_ids": [1]},
                {"id": "s02", "start_ms": 30000, "end_ms": 60000, "label": "要点",
                 "suggested_action": "merge", "merge_into": "s01", "candidate_slide_ids": [2]},
            ]
        }
        assert validate_confirmed_segments(pending) is True

    def test_merge_without_target(self):
        pending = {
            "segments": [
                {"id": "s01", "start_ms": 0, "end_ms": 30000, "label": "开篇",
                 "suggested_action": "keep", "candidate_slide_ids": [1]},
                {"id": "s02", "start_ms": 30000, "end_ms": 60000, "label": "要点",
                 "suggested_action": "merge", "merge_into": "s99", "candidate_slide_ids": [2]},
            ]
        }
        assert validate_confirmed_segments(pending) is False

    def test_empty_segments(self):
        assert validate_confirmed_segments({"segments": []}) is False


class TestTranscriptDrivenSegmentation:
    """分段边界由 transcript 内容决定，不由候选图 capture_ms 决定。"""

    def _make_candidates(self, times_ms: list[int]) -> SlideSet:
        return SlideSet(slides=[
            Slide(slide_index=i + 1, image_path=f"img{i}.png", start_ms=t, end_ms=t + 1000,
                  capture_ms=t, confidence=0.8, hash="0" * 16, edge_density=0.5)
            for i, t in enumerate(times_ms)
        ])

    def _make_transcript(self, segments: list[tuple[int, int, str]]) -> Transcript:
        return Transcript(
            backend="test", language="zh",
            segments=[TranscriptSegment(start_ms=s, end_ms=e, text=t) for s, e, t in segments],
        )

    def test_transcript_driven_boundaries_not_candidate_capture_ms(self):
        """分段边界由 transcript 内容决定，不由候选图 capture_ms 决定。"""
        candidates = self._make_candidates([5000, 10000, 15000])
        transcript = self._make_transcript([
            (0, 40000, "今天我们来聊聊智能办公本的选购要点。首先看价位段。"),
        ])
        result = generate_pending_segments(candidates, transcript, duration_sec=40)
        # 应该只有 1 个段，边界是 0-40000，不是 5000/10000/15000
        assert len(result["segments"]) == 1
        seg = result["segments"][0]
        assert seg["start_ms"] == 0
        assert seg["end_ms"] == 40000

    def test_dense_candidates_dont_fragment_segments(self):
        """密集候选图不会把一个语义段拆成多个。"""
        candidates = self._make_candidates([5000, 10000, 15000, 20000, 25000])
        transcript = self._make_transcript([
            (0, 30000, "第一部分介绍产品A的特点和优势。"),
            (30000, 60000, "第二部分介绍产品B的特点和优势。"),
        ])
        result = generate_pending_segments(candidates, transcript, duration_sec=60)
        # 不应是 5 个（候选图数量）；短文本片段自然合并为 1-2 个段
        assert len(result["segments"]) <= 2
        assert result["segments"][0]["start_ms"] == 0

    def test_short_transcript_segments_merged_by_density(self):
        """短 transcript 片段按内容密度合并。"""
        candidates = self._make_candidates([0, 30000])
        # 6 条 SRT 片段，每条 1-2 秒，但讲同一话题
        transcript = self._make_transcript([
            (0, 2000, "大家好"),
            (2000, 4000, "这里是智玩先锋"),
            (4000, 6000, "买数码产品"),
            (6000, 8000, "我的原则只有一个"),
            (8000, 10000, "不交智商税"),
            (10000, 30000, "今天这期是全网最硬核的智能办公本避坑指南"),
        ])
        result = generate_pending_segments(candidates, transcript, duration_sec=30)
        # 前 5 个短片段应合并为 1 个段
        assert len(result["segments"]) <= 2

    def test_segment_includes_candidate_slide_ids(self):
        """分段仍记录其时间范围内的候选图 ID。"""
        candidates = self._make_candidates([5000, 15000, 25000])
        transcript = self._make_transcript([
            (0, 30000, "第一段内容。"),
        ])
        result = generate_pending_segments(candidates, transcript, duration_sec=30)
        seg = result["segments"][0]
        assert len(seg["candidate_slide_ids"]) == 3


class TestMergeTimeRange:
    """merge 段的时间范围扩展到目标段。"""

    def test_merge_extends_target_end_ms(self):
        from videotodoc.pipeline import _apply_merge_extensions
        segments = [
            {"id": "s01", "start_ms": 0, "end_ms": 30000, "suggested_action": "keep",
             "candidate_slide_ids": [1], "label": "a"},
            {"id": "s02", "start_ms": 30000, "end_ms": 35000, "suggested_action": "merge",
             "merge_into": "s01", "candidate_slide_ids": [2], "label": "b"},
            {"id": "s03", "start_ms": 35000, "end_ms": 60000, "suggested_action": "keep",
             "candidate_slide_ids": [3], "label": "c"},
        ]
        result = _apply_merge_extensions(segments)
        s01 = next(s for s in result if s["id"] == "s01")
        assert s01["end_ms"] == 35000  # 扩展到 s02 的 end_ms

    def test_merge_extends_candidate_slide_ids(self):
        from videotodoc.pipeline import _apply_merge_extensions
        segments = [
            {"id": "s01", "start_ms": 0, "end_ms": 20000, "suggested_action": "keep",
             "candidate_slide_ids": [1], "label": "a"},
            {"id": "s02", "start_ms": 20000, "end_ms": 30000, "suggested_action": "merge",
             "merge_into": "s01", "candidate_slide_ids": [2, 3], "label": "b"},
        ]
        result = _apply_merge_extensions(segments)
        s01 = next(s for s in result if s["id"] == "s01")
        assert 1 in s01["candidate_slide_ids"]
        assert 2 in s01["candidate_slide_ids"]
        assert 3 in s01["candidate_slide_ids"]
        assert s01["end_ms"] == 30000

    def test_no_merge_segments_unchanged(self):
        from videotodoc.pipeline import _apply_merge_extensions
        segments = [
            {"id": "s01", "start_ms": 0, "end_ms": 30000, "suggested_action": "keep",
             "candidate_slide_ids": [1], "label": "a"},
            {"id": "s02", "start_ms": 30000, "end_ms": 60000, "suggested_action": "keep",
             "candidate_slide_ids": [2], "label": "b"},
        ]
        result = _apply_merge_extensions(segments)
        s01 = next(s for s in result if s["id"] == "s01")
        assert s01["end_ms"] == 30000  # 不变
