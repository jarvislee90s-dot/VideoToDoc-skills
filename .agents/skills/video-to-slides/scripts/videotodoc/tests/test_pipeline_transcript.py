from videotodoc.pipeline import _transcript_from_external


class TestTranscriptFromExternal:
    def test_seconds_float_list(self):
        data = [{"start": 1.5, "end": 3.0, "text": "hi"}, {"start": 3.0, "end": 4.5, "text": "ok"}]
        t = _transcript_from_external(data, "zh")
        assert t.segments[0].start_ms == 1500
        assert t.segments[0].end_ms == 3000
        assert isinstance(t.segments[0].start_ms, int)

    def test_ms_dict_segments(self):
        data = {"segments": [{"start_ms": 1000, "end_ms": 2000, "text": "x"}]}
        t = _transcript_from_external(data, "zh")
        assert t.segments[0].start_ms == 1000

    def test_empty(self):
        assert _transcript_from_external([], "zh").segments == []


class TestAutoClassifyVideo:
    def test_classify_video_importable_from_pipeline(self):
        """classify_video 可从 pipeline 模块导入（验证导入链）。"""
        import videotodoc.pipeline as pipeline_mod
        assert hasattr(pipeline_mod, "classify_video")

    def test_auto_classify_writes_back_settings(self, monkeypatch):
        """video_type=auto 时 process_video 调 classify_video 并写回 settings.video_type。"""
        import videotodoc.pipeline as pipeline_mod
        import videotodoc.slides as slides_mod
        from videotodoc.config import Settings
        from pathlib import Path

        # monkeypatch classify_video 返回 talking_head（pipeline 已按名导入，需 patch pipeline 命名空间）
        monkeypatch.setattr(pipeline_mod, "classify_video", lambda vp: "talking_head")
        # monkeypatch 下游函数避免真实处理
        monkeypatch.setattr(pipeline_mod, "extract_audio", lambda *a, **k: Path("/tmp/a.wav"))
        monkeypatch.setattr(pipeline_mod, "probe_duration_ms", lambda vp: 60000)
        monkeypatch.setattr(pipeline_mod, "capture_interval_for_duration", lambda sec: 15)
        monkeypatch.setattr(pipeline_mod, "transcribe_audio", lambda *a, **k: pipeline_mod._transcript_from_external([], "zh"))
        monkeypatch.setattr(pipeline_mod, "detect_slides", lambda *a, **k: pipeline_mod.SlideSet(slides=[]))
        monkeypatch.setattr(pipeline_mod, "trim_candidates_by_transcript", lambda *a, **k: pipeline_mod.SlideSet(slides=[]))
        monkeypatch.setattr(pipeline_mod, "deduplicate_slides", lambda *a, **k: pipeline_mod.SlideSet(slides=[]))
        monkeypatch.setattr(pipeline_mod, "materialize_selected_slides", lambda slides, d: slides)
        monkeypatch.setattr(pipeline_mod, "estimate_sync_offset_ms", lambda *a, **k: 0)
        monkeypatch.setattr(pipeline_mod, "align_sections", lambda *a, **k: [])
        monkeypatch.setattr(pipeline_mod, "write_json", lambda *a, **k: None)
        monkeypatch.setattr(pipeline_mod, "render_original_markdown", lambda *a, **k: Path("/tmp/m.md"))
        monkeypatch.setattr(pipeline_mod, "render_compact_markdown", lambda *a, **k: None)
        monkeypatch.setattr(pipeline_mod, "ensure_semantic_markdown", lambda *a, **k: None)
        monkeypatch.setattr(pipeline_mod, "write_quality_report", lambda *a, **k: None)
        monkeypatch.setattr(pipeline_mod, "file_md5", lambda p: "abc123")
        monkeypatch.setattr(pipeline_mod, "slugify", lambda s: "test")

        settings = Settings()
        assert settings.video_type == "auto"
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            vp = Path(tmpdir) / "v.mp4"
            vp.write_bytes(b"fake")
            pipeline_mod.process_video(vp, Path(tmpdir), settings, run_dir=Path(tmpdir) / "run")
        assert settings.video_type == "talking_head"
