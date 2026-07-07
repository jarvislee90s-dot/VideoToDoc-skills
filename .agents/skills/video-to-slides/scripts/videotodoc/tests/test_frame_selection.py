from pathlib import Path
from unittest.mock import patch
from videotodoc.config import Settings
from videotodoc.slides import choose_capture_time


def test_settings_has_frame_drift_back_seconds():
    s = Settings()
    assert hasattr(s, "frame_drift_back_seconds")
    assert s.frame_drift_back_seconds == 2.0


def test_settings_has_min_edge_density():
    s = Settings()
    assert hasattr(s, "min_edge_density")
    assert s.min_edge_density == 0.02


def _make_frame(path: Path, *, dense: bool) -> None:
    """构造测试用帧：dense=True 时画满文字/线条，dense=False 时纯白。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (200, 200), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    if dense:
        # 画密集线条模拟文字/PPT 内容
        for y in range(20, 180, 10):
            draw.line([(10, y), (190, y)], fill=(0, 0, 0), width=2)
        draw.text((20, 20), "Hello World Dense Content", fill=(0, 0, 0))
    # dense=False 时保持纯白（edge_density ~ 0）
    img.save(path)


def test_choose_capture_time_drifts_forward_on_low_density(tmp_path):
    """默认帧信息密度低时，应向前（时间更早）漂移找到高密度帧。"""
    video_path = tmp_path / "v.mp4"
    video_path.write_bytes(b"fake")

    settings = Settings(
        capture_margin_ms=500,
        frame_drift_back_seconds=2.0,
        min_edge_density=0.02,
    )

    # segment [8000ms, 10000ms]，默认截图点是 9500ms
    # 9500ms 低密度（过渡/纯白），往前 9000ms 高密度（有内容）
    def mock_extract_frame(vp, ms, out_path, precise=True):
        _make_frame(out_path, dense=(ms == 9000))

    with patch("videotodoc.slides.extract_frame", side_effect=mock_extract_frame):
        capture_ms, confidence = choose_capture_time(video_path, 8000, 10000, settings)

    # 应选中 9000ms，而非默认的 9500ms
    assert capture_ms == 9000
    assert confidence > 0.5


def test_choose_capture_time_keeps_default_when_dense(tmp_path):
    """默认帧信息密度足够时，不漂移。"""
    video_path = tmp_path / "v.mp4"
    video_path.write_bytes(b"fake")

    settings = Settings(
        capture_margin_ms=500,
        frame_drift_back_seconds=2.0,
        min_edge_density=0.02,
    )

    def mock_extract_frame(vp, ms, out_path, precise=True):
        _make_frame(out_path, dense=True)

    with patch("videotodoc.slides.extract_frame", side_effect=mock_extract_frame):
        capture_ms, confidence = choose_capture_time(video_path, 8000, 10000, settings)

    assert capture_ms == 9500
    assert confidence > 0.5


class TestTrimParagraphDominant:
    def _settings(self):
        return Settings(capture_margin_ms=500)

    def test_slide_time_range_uses_segment_boundary(self, tmp_path):
        """trim 后 slide 的 start/end 应等于 transcript 段边界，而非候选图窗口。"""
        from videotodoc.models import Slide, SlideSet, Transcript, TranscriptSegment
        from videotodoc.slides import trim_candidates_by_transcript
        seg = TranscriptSegment(start_ms=0, end_ms=22000, text="一段话。")
        transcript = Transcript(backend="reused", language="zh", segments=[seg])
        # 候选图窗口是 [0, 15500]，capture=15000（场景窗口末尾）
        cand = SlideSet(slides=[Slide(
            slide_index=1, image_path="/tmp/c1.png", start_ms=0, end_ms=15500,
            capture_ms=15000, confidence=0.8, hash="0" * 16, edge_density=0.05,
        )])
        out = trim_candidates_by_transcript(cand, transcript, tmp_path / "v.mp4", tmp_path, self._settings())
        s = out.slides[0]
        # 段边界，不是候选图窗口
        assert s.start_ms == 0
        assert s.end_ms == 22000
        # capture 保留原始候选图截图时刻（新行为：不再覆盖为段末-margin）
        assert s.capture_ms == 15000

    def test_talking_head_no_candidate_extracts_end_frame(self, tmp_path, monkeypatch):
        """talking_head 段内无候选图 → 段末取帧，不再跳过。"""
        from videotodoc.models import Slide, SlideSet, Transcript, TranscriptSegment
        import videotodoc.slides as slides_mod
        from videotodoc.slides import trim_candidates_by_transcript
        def _fake_extract(video_path, capture_ms, output_path, precise=True):
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(b"")
            return None
        monkeypatch.setattr(slides_mod, "extract_frame", _fake_extract)
        seg = TranscriptSegment(start_ms=0, end_ms=20000, text="纯口播段。")
        transcript = Transcript(backend="reused", language="zh", segments=[seg])
        cand = SlideSet(slides=[])
        settings = self._settings()
        settings.video_type = "talking_head"
        out = trim_candidates_by_transcript(cand, transcript, tmp_path / "v.mp4", tmp_path, settings)
        assert len(out.slides) == 1
        assert out.slides[0].capture_ms == 20000 - 500
        assert out.slides[0].start_ms == 0 and out.slides[0].end_ms == 20000
