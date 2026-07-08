"""段内多候选 + 匹配窗口测试（任务 8）。"""

from pathlib import Path
from unittest.mock import patch

from videotodoc.models import Slide, SlideSet, Transcript, TranscriptSegment
from videotodoc.config import Settings
from videotodoc.slides import trim_candidates_by_transcript


def _make_slide(capture_ms: int, edge: float = 0.3, ocr: str = "") -> Slide:
    return Slide(
        slide_index=0, image_path=f"/tmp/cand_{capture_ms}.png",
        start_ms=capture_ms - 1000, end_ms=capture_ms + 1000,
        capture_ms=capture_ms, confidence=0.9, hash="0" * 16,
        edge_density=edge, ocr_text=ocr,
    )


def _make_transcript_with_segment(start: int, end: int, text: str) -> Transcript:
    return Transcript(backend="test", language="zh", segments=[
        TranscriptSegment(start_ms=start, end_ms=end, text=text),
    ])


def test_trim_keep_all_false_produces_one_slide(tmp_path: Path) -> None:
    """默认（keep_all=False）每段 1 张主图。"""
    video = tmp_path / "v.mp4"
    video.write_bytes(b"")
    transcript = _make_transcript_with_segment(0, 30000, "推导 LLM 大语言模型")
    candidates = SlideSet(slides=[
        _make_slide(20000, edge=0.5, ocr="LLM 推导"),
        _make_slide(28000, edge=0.8, ocr="LLM 大语言"),
    ])
    settings = Settings(keep_all_segment_candidates=False, match_window_sec=5)
    with patch("videotodoc.slides.capture_frames_opencv", return_value={}):
        result = trim_candidates_by_transcript(candidates, transcript, video, tmp_path, settings)
    assert len(result.slides) == 1
    main = result.slides[0]
    # 评分最高的（edge 0.8 + ocr 匹配）是第二张
    assert main.edge_density == 0.8


def test_trim_keep_all_true_produces_n_slides_in_time_order(tmp_path: Path) -> None:
    """keep_all=True 段内 N 张图，按时间顺序排列。"""
    video = tmp_path / "v.mp4"
    video.write_bytes(b"")
    transcript = _make_transcript_with_segment(0, 30000, "推导 LLM 大语言模型")
    # 3 张候选，时间 15000/20000/28000，OCR 匹配度 28000 最高
    candidates = SlideSet(slides=[
        _make_slide(15000, edge=0.4, ocr=""),
        _make_slide(20000, edge=0.5, ocr="LLM"),
        _make_slide(28000, edge=0.8, ocr="LLM 大语言"),  # 主图
    ])
    settings = Settings(keep_all_segment_candidates=True, match_window_sec=5)
    with patch("videotodoc.slides.capture_frames_opencv", return_value={}):
        result = trim_candidates_by_transcript(candidates, transcript, video, tmp_path, settings)
    assert len(result.slides) == 3
    # 段内时间顺序：15000, 20000, 28000
    assert result.slides[0].capture_ms == 15000
    assert result.slides[1].capture_ms == 20000
    assert result.slides[2].capture_ms == 28000
    # 主图（28000）保留原位置不前置


def test_trim_match_window_filters_out_of_window(tmp_path: Path) -> None:
    """段 [0, 30000]，W=5s → 只看 [25000, 30000) 内的候选。"""
    video = tmp_path / "v.mp4"
    video.write_bytes(b"")
    transcript = _make_transcript_with_segment(0, 30000, "推导 LLM")
    candidates = SlideSet(slides=[
        _make_slide(10000, edge=0.5, ocr=""),  # 段中段，不在 [25000, 30000) 内
        _make_slide(28000, edge=0.8, ocr="LLM"),  # 在窗口内
    ])
    settings = Settings(keep_all_segment_candidates=False, match_window_sec=5)
    with patch("videotodoc.slides.capture_frames_opencv", return_value={}):
        result = trim_candidates_by_transcript(candidates, transcript, video, tmp_path, settings)
    assert len(result.slides) == 1
    assert result.slides[0].capture_ms == 28000
