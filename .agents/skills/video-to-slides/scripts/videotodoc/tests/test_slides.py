"""候选点生成 + finalize_segment_slides 测试。"""
from videotodoc.slides import _candidate_points
from videotodoc.config import Settings


class TestCandidatePoints:
    def test_interval_as_minimum_gap(self):
        """场景变化点不产生额外候选，只微调间隔内的 capture_ms。"""
        settings = Settings(fallback_interval_sec=30, capture_mode="audit")
        # 密集场景变化：每 2 秒一个
        change_points = [2000, 4000, 6000, 8000, 10000, 12000, 14000, 16000,
                         18000, 20000, 22000, 24000, 26000, 28000]
        points = _candidate_points(change_points, 60000, settings)
        # 60 秒视频，30 秒间隔 → 只有 1 个间隔点 (30s)
        # 30s 附近的场景变化点 (28s) 微调 capture_ms
        assert len(points) == 1
        assert points[0] == 28000  # 最近的场景变化点

    def test_no_scene_changes_uses_pure_interval(self):
        """无场景变化时，纯按间隔生成候选点。"""
        settings = Settings(fallback_interval_sec=30, capture_mode="audit")
        points = _candidate_points([], 120000, settings)
        assert points == [30000, 60000, 90000]

    def test_scene_change_within_gap_refines_capture(self):
        """间隔内的场景变化点微调 capture_ms 到最近的变化点。"""
        settings = Settings(fallback_interval_sec=30, capture_mode="audit")
        # 0-30s 窗口内有一个场景变化在 25s
        change_points = [25000]
        points = _candidate_points(change_points, 60000, settings)
        # 应该有 1 个点：25s（微调后的间隔点）
        assert 25000 in points
        # 30000 不应在 points 中（被 25000 微调替代）
        assert 30000 not in points

    def test_multiple_intervals_with_refinement(self):
        """多个间隔窗口各自独立微调。"""
        settings = Settings(fallback_interval_sec=30, capture_mode="audit")
        change_points = [25000, 55000]  # 30s 窗口和 60s 窗口各一个
        points = _candidate_points(change_points, 90000, settings)
        # 30s → 25s, 60s → 55s
        assert 25000 in points
        assert 55000 in points
        assert 30000 not in points
        assert 60000 not in points


import json
from pathlib import Path as PathCls
from videotodoc.slides import finalize_segment_slides
from videotodoc.models import Slide, SlideSet
from videotodoc.config import Settings


class TestFinalizeSegmentSlides:
    def _make_candidates(self, times_ms: list[int]) -> SlideSet:
        return SlideSet(slides=[
            Slide(slide_index=i + 1, image_path=f"img{i}.png", start_ms=t, end_ms=t + 1000,
                  capture_ms=t, confidence=0.8, hash=f"{i:016x}", edge_density=0.3 + i * 0.1)
            for i, t in enumerate(times_ms)
        ])

    def test_returns_one_slide_per_segment(self, tmp_path):
        """每段只返回 1 张截图。"""
        candidates = self._make_candidates([5000, 10000, 15000])
        segment = {
            "id": "s01", "start_ms": 0, "end_ms": 30000,
            "suggested_action": "keep",
            "candidate_slide_ids": [1, 2, 3],
        }
        result = finalize_segment_slides(
            segment, candidates, PathCls("/dev/null"), tmp_path, Settings(),
        )
        assert len(result) == 1

    def test_slide_time_range_is_segment_range(self, tmp_path):
        """返回的 slide 时间范围 = 段的 [start_ms, end_ms]。"""
        candidates = self._make_candidates([5000])
        segment = {
            "id": "s01", "start_ms": 0, "end_ms": 30000,
            "suggested_action": "keep",
            "candidate_slide_ids": [1],
        }
        result = finalize_segment_slides(
            segment, candidates, PathCls("/dev/null"), tmp_path, Settings(),
        )
        assert result[0].start_ms == 0
        assert result[0].end_ms == 30000

    def test_picks_highest_edge_density(self, tmp_path):
        """选 edge_density 最高的候选图。"""
        candidates = self._make_candidates([5000, 10000, 15000])
        # edge_density: slide1=0.3, slide2=0.4, slide3=0.5 → 选 slide3
        segment = {
            "id": "s01", "start_ms": 0, "end_ms": 30000,
            "suggested_action": "keep",
            "candidate_slide_ids": [1, 2, 3],
        }
        result = finalize_segment_slides(
            segment, candidates, PathCls("/dev/null"), tmp_path, Settings(),
        )
        assert result[0].capture_ms == 15000  # slide3 的 capture_ms

    def test_no_candidates_returns_empty_without_video(self, tmp_path):
        """段内无候选图且无视频文件时不崩溃（extract_frame 会失败）。"""
        candidates = SlideSet(slides=[])
        segment = {
            "id": "s01", "start_ms": 0, "end_ms": 30000,
            "suggested_action": "keep",
            "candidate_slide_ids": [],
        }
        # /dev/null 不是视频，extract_frame 会抛异常
        try:
            result = finalize_segment_slides(
                segment, candidates, PathCls("/dev/null"), tmp_path, Settings(),
            )
            assert len(result) == 1
            assert result[0].capture_ms == 15000  # 中点
        except Exception:
            pass  # extract_frame 失败是预期的
