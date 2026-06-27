"""测试 finalize_video 缓存文件 video_hash 匹配逻辑。"""
import hashlib
import json
from pathlib import Path

import pytest

from videotodoc.pipeline import _find_matching_cache_file
from videotodoc.utils import VideoToDocError


def _make_hash(content: bytes) -> str:
    return hashlib.md5(content).hexdigest()


class TestFindMatchingCacheFile:
    def test_match_by_filename_prefix(self, tmp_path):
        """文件名以 video_hash 前12位开头时应匹配成功。"""
        video = tmp_path / "v.mp4"
        video.write_bytes(b"video content A")
        vhash = _make_hash(b"video content A")
        short = vhash[:12]

        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        (cache_dir / f"{short}_mode.candidates.json").write_text(
            json.dumps({"slides": [], "metadata": {}})
        )
        (cache_dir / f"{'b' * 12}_other.candidates.json").write_text(
            json.dumps({"slides": [], "metadata": {}})
        )

        result = _find_matching_cache_file(
            list(cache_dir.glob("*.candidates.json")),
            video,
            "candidates",
        )
        assert result.name.startswith(short)

    def test_match_by_metadata_video_hash(self, tmp_path):
        """文件名不匹配但 metadata.video_hash 匹配时应成功。"""
        video = tmp_path / "v.mp4"
        video.write_bytes(b"video content B")
        vhash = _make_hash(b"video content B")

        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        (cache_dir / "random_name.candidates.json").write_text(
            json.dumps({"slides": [], "metadata": {"video_hash": vhash}})
        )
        (cache_dir / "wrong.candidates.json").write_text(
            json.dumps({"slides": [], "metadata": {"video_hash": "deadbeef"}})
        )

        result = _find_matching_cache_file(
            list(cache_dir.glob("*.candidates.json")),
            video,
            "candidates",
        )
        data = json.loads(result.read_text())
        assert data["metadata"]["video_hash"] == vhash

    def test_match_by_toplevel_video_hash(self, tmp_path):
        """顶层 video_hash 字段匹配时应成功。"""
        video = tmp_path / "v.mp4"
        video.write_bytes(b"video content C")
        vhash = _make_hash(b"video content C")

        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        (cache_dir / "some_file.candidates.json").write_text(
            json.dumps({"video_hash": vhash, "slides": []})
        )
        (cache_dir / "other.candidates.json").write_text(
            json.dumps({"video_hash": "xxxx", "slides": []})
        )

        result = _find_matching_cache_file(
            list(cache_dir.glob("*.candidates.json")),
            video,
            "candidates",
        )
        data = json.loads(result.read_text())
        assert data["video_hash"] == vhash

    def test_single_file_fallback(self, tmp_path):
        """只有一个缓存文件时兜底使用（向后兼容）。"""
        video = tmp_path / "v.mp4"
        video.write_bytes(b"video content D")

        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        (cache_dir / "old_cache.candidates.json").write_text(
            json.dumps({"slides": [], "metadata": {}})
        )

        result = _find_matching_cache_file(
            list(cache_dir.glob("*.candidates.json")),
            video,
            "candidates",
        )
        assert result.name == "old_cache.candidates.json"

    def test_multiple_no_match_raises_error(self, tmp_path):
        """多个缓存文件均不匹配时应抛出 VideoToDocError。"""
        video = tmp_path / "v.mp4"
        video.write_bytes(b"video content E")
        vhash = _make_hash(b"video content E")

        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        (cache_dir / f"{'a' * 12}_x.candidates.json").write_text(
            json.dumps({"slides": [], "metadata": {"video_hash": "aaa"}})
        )
        (cache_dir / f"{'b' * 12}_y.candidates.json").write_text(
            json.dumps({"slides": [], "metadata": {"video_hash": "bbb"}})
        )

        with pytest.raises(VideoToDocError, match="无匹配"):
            _find_matching_cache_file(
                list(cache_dir.glob("*.candidates.json")),
                video,
                "candidates",
            )

    def test_no_files_raises_error(self, tmp_path):
        """无缓存文件时应抛出 VideoToDocError。"""
        video = tmp_path / "v.mp4"
        video.write_bytes(b"video content F")

        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()

        with pytest.raises(VideoToDocError, match="找不到"):
            _find_matching_cache_file(
                list(cache_dir.glob("*.candidates.json")),
                video,
                "candidates",
            )

    def test_transcript_file_matching(self, tmp_path):
        """transcript 文件同样按 video_hash 前缀匹配。"""
        video = tmp_path / "v.mp4"
        video.write_bytes(b"video content G")
        vhash = _make_hash(b"video content G")
        short = vhash[:12]

        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        (cache_dir / f"{short}_whisper_base.transcript.json").write_text(
            json.dumps({"segments": []})
        )
        (cache_dir / f"{'c' * 12}_qwen.transcript.json").write_text(
            json.dumps({"segments": []})
        )

        result = _find_matching_cache_file(
            list(cache_dir.glob("*.transcript.json")),
            video,
            "transcript",
        )
        assert result.name.startswith(short)

    def test_filename_prefix_priority_over_content(self, tmp_path):
        """文件名匹配优先于内容匹配，返回文件名匹配的文件。"""
        video = tmp_path / "v.mp4"
        video.write_bytes(b"video content H")
        vhash = _make_hash(b"video content H")
        short = vhash[:12]

        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        match_file = cache_dir / f"{short}_mode.candidates.json"
        match_file.write_text(json.dumps({"slides": [], "metadata": {"video_hash": vhash}}))
        other_file = cache_dir / "other.candidates.json"
        other_file.write_text(json.dumps({"slides": [], "metadata": {"video_hash": vhash}}))

        result = _find_matching_cache_file(
            list(cache_dir.glob("*.candidates.json")),
            video,
            "candidates",
        )
        assert result == match_file

    def test_wrong_file_selected_without_hash_check(self, tmp_path):
        """验证旧 bug：无 hash 校验时 [0] 可能选错文件（按文件名排序第一个不一定对）。"""
        video = tmp_path / "v.mp4"
        video.write_bytes(b"video content I")
        vhash = _make_hash(b"video content I")
        short = vhash[:12]

        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        wrong = cache_dir / f"{'a' * 12}_wrong.candidates.json"
        wrong.write_text(json.dumps({"slides": [{"slide_index": 999, "image_path": "/wrong.png",
                                                  "start_ms": 0, "end_ms": 1000, "capture_ms": 500,
                                                  "confidence": 0.1}], "metadata": {"video_hash": "aaa"}}))
        right = cache_dir / f"{short}_right.candidates.json"
        right.write_text(json.dumps({"slides": [{"slide_index": 1, "image_path": "/right.png",
                                                   "start_ms": 0, "end_ms": 1000, "capture_ms": 500,
                                                   "confidence": 0.9}], "metadata": {"video_hash": vhash}}))

        result = _find_matching_cache_file(
            sorted(cache_dir.glob("*.candidates.json")),
            video,
            "candidates",
        )
        assert result == right
        data = json.loads(result.read_text())
        assert data["slides"][0]["image_path"] == "/right.png"
