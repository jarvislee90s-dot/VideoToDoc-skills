"""验证 finalize_video 优先使用阶段 0 产出的 transcript_merged.json。

RED: 当前实现只读 cache/*.transcript.json，不检查 run_dir/transcript_merged.json。
GREEN: 补 prefer-merged 逻辑后，merged 存在时优先用它。
"""
import hashlib
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from videotodoc import pipeline


def _make_hash(content: bytes) -> str:
    return hashlib.md5(content).hexdigest()


def _setup_fixture(tmp_path: Path) -> tuple[Path, str]:
    """建最小 finalize fixture：confirmed_segments + candidates cache + video。

    返回 (video_path, video_hash)。
    """
    video_content = b"fake video content for testing"
    video = tmp_path / "test.mp4"
    video.write_bytes(video_content)
    vhash = _make_hash(video_content)
    short = vhash[:12]

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    # candidates cache（hash 匹配）
    (cache_dir / f"{short}.candidates.json").write_text(
        json.dumps({"slides": [], "metadata": {"video_hash": vhash}})
    )
    (tmp_path / "confirmed_segments.json").write_text(
        json.dumps({
            "video_path": str(video.resolve()),
            "segments": [{"id": "s00", "suggested_action": "keep", "start_ms": 0, "end_ms": 1000, "candidate_slide_ids": []}],
            "video_title": "test",
        })
    )
    return video, short


def test_finalize_prefers_merged_when_exists(tmp_path: Path):
    """merged 存在时 _transcript_from_external 收到的是 merged 的数据，不是 cache。"""
    video, short = _setup_fixture(tmp_path)

    # merged 有独特内容
    (tmp_path / "transcript_merged.json").write_text(
        json.dumps({"segments": [{"start": 0, "end": 1000, "text": "MERGED_TEXT"}]})
    )
    # cache transcript 内容不同（hash 匹配）
    (tmp_path / "cache" / f"{short}.transcript.json").write_text(
        json.dumps({"segments": [{"start": 0, "end": 1000, "text": "CACHE_TEXT"}]})
    )

    received_data = []

    def spy_transcript(data, language):
        received_data.append(data)
        return MagicMock(segments=[])

    with patch.object(pipeline, "_transcript_from_external", spy_transcript), \
         patch.object(pipeline, "slides_from_dict", return_value=MagicMock(slides=[])), \
         patch.object(pipeline, "finalize_segment_slides", return_value=[]), \
         patch.object(pipeline, "cross_segment_dedupe"), \
         patch.object(pipeline, "align_sections", return_value=[]), \
         patch.object(pipeline, "render_original_markdown"), \
         patch.object(pipeline, "render_compact_markdown"), \
         patch.object(pipeline, "ensure_semantic_markdown"), \
         patch("videotodoc.pipeline.SlideSet", return_value=MagicMock(slides=[])), \
         patch("videotodoc.pipeline.shutil.copy2"):
        try:
            from videotodoc.config import Settings
            settings = Settings(transcript_path=str(tmp_path / "transcript_merged.json"))
            pipeline.finalize_video(tmp_path, settings)
        except Exception:
            pass

    assert len(received_data) > 0, "_transcript_from_external 应被调用"
    first_call = received_data[0]
    # _transcript_from_external 接收原始 dict/list，提取 text
    if isinstance(first_call, list):
        texts = [s.get("text", "") for s in first_call if isinstance(s, dict)]
    elif isinstance(first_call, dict):
        texts = [s.get("text", "") for s in first_call.get("segments", [])]
    else:
        texts = []
    assert any("MERGED_TEXT" in t for t in texts), (
        f"应收到 merged 数据（MERGED_TEXT），实际收到：{first_call}"
    )


def test_finalize_falls_back_to_cache_when_no_merged(tmp_path: Path):
    """merged 不存在时回退读 cache（CACHE_TEXT）。"""
    video, short = _setup_fixture(tmp_path)
    # 不创建 transcript_merged.json
    (tmp_path / "cache" / f"{short}.transcript.json").write_text(
        json.dumps({"segments": [{"start": 0, "end": 1000, "text": "CACHE_TEXT"}]})
    )

    received_data = []

    def spy_transcript(data, language):
        received_data.append(data)
        return MagicMock(segments=[])

    with patch.object(pipeline, "_transcript_from_external", spy_transcript), \
         patch.object(pipeline, "slides_from_dict", return_value=MagicMock(slides=[])), \
         patch.object(pipeline, "finalize_segment_slides", return_value=[]), \
         patch.object(pipeline, "cross_segment_dedupe"), \
         patch.object(pipeline, "align_sections", return_value=[]), \
         patch.object(pipeline, "render_original_markdown"), \
         patch.object(pipeline, "render_compact_markdown"), \
         patch.object(pipeline, "ensure_semantic_markdown"), \
         patch("videotodoc.pipeline.SlideSet", return_value=MagicMock(slides=[])), \
         patch("videotodoc.pipeline.shutil.copy2"):
        try:
            from videotodoc.config import Settings
            settings = Settings(transcript_path=str(tmp_path / "transcript.json"))
            pipeline.finalize_video(tmp_path, settings)
        except Exception:
            pass

    assert len(received_data) > 0, "_transcript_from_external 应被调用"
    first_call = received_data[0]
    if isinstance(first_call, list):
        texts = [s.get("text", "") for s in first_call if isinstance(s, dict)]
    elif isinstance(first_call, dict):
        texts = [s.get("text", "") for s in first_call.get("segments", [])]
    else:
        texts = []
    assert any("CACHE_TEXT" in t for t in texts), (
        f"merged 不存在时应回退读 cache（CACHE_TEXT），实际收到：{first_call}"
    )
