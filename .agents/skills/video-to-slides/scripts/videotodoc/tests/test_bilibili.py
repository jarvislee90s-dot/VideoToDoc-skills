import importlib.util
from pathlib import Path

# 显式从 video-summary/scripts/process.py 加载，避免与 video-to-slides/scripts/process.py 冲突
_VS_PROCESS = Path(__file__).resolve().parents[4] / "video-summary" / "scripts" / "process.py"
_spec = importlib.util.spec_from_file_location("vs_process", _VS_PROCESS)
vs_process = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vs_process)


class TestBilibiliRiskControl:
    def test_detect_v_voucher_present(self):
        data = {"code": 0, "data": {"v_voucher": "voucher_abc"}}
        assert vs_process._bilibili_detect_v_voucher(data) is True

    def test_detect_v_voucher_absent_with_dash(self):
        data = {"code": 0, "data": {"dash": {"video": [], "audio": []}}}
        assert vs_process._bilibili_detect_v_voucher(data) is False

    def test_detect_v_voucher_error_code(self):
        data = {"code": -404, "message": "不存在"}
        assert vs_process._bilibili_detect_v_voucher(data) is False


class TestCookiesFromBrowser:
    def test_argparse_accepts_cookies_from_browser(self):
        """argparse 接受 --cookies-from-browser 参数。"""
        import sys
        old_argv = sys.argv
        sys.argv = ["process.py", "https://www.bilibili.com/video/BV123",
                    "--cookies-from-browser", "chrome"]
        try:
            parser = vs_process._build_arg_parser()
            args = parser.parse_args()
            assert args.cookies_from_browser == "chrome"
        finally:
            sys.argv = old_argv

    def test_argparse_default_chrome(self):
        """默认不传 cookies-from-browser 时为 chrome（B 站风控需登录态）。"""
        import sys
        old_argv = sys.argv
        sys.argv = ["process.py", "https://www.bilibili.com/video/BV123"]
        try:
            parser = vs_process._build_arg_parser()
            args = parser.parse_args()
            assert args.cookies_from_browser == "chrome"
        finally:
            sys.argv = old_argv


import json


class TestSrtTimestampParsing:
    def test_parse_srt_with_timestamps(self, tmp_path):
        """SRT 文件解析出 start_ms 和 end_ms。"""
        srt_content = "1\n00:00:01,500 --> 00:00:03,200\n你好世界\n\n2\n00:00:03,500 --> 00:00:05,000\n测试字幕\n"
        srt_path = tmp_path / "test.srt"
        srt_path.write_text(srt_content, encoding="utf-8")
        text, segments = vs_process._parse_subtitle_file(srt_path)
        assert text is not None
        assert len(segments) == 2
        assert segments[0]["start_ms"] == 1500
        assert segments[0]["end_ms"] == 3200
        assert segments[1]["start_ms"] == 3500
        assert segments[1]["end_ms"] == 5000

    def test_parse_srt_text_content(self, tmp_path):
        """SRT 解析的文本内容正确。"""
        srt_content = "1\n00:00:00,000 --> 00:00:02,000\n第一句\n"
        srt_path = tmp_path / "test.srt"
        srt_path.write_text(srt_content, encoding="utf-8")
        text, segments = vs_process._parse_subtitle_file(srt_path)
        assert "第一句" in text
        assert segments[0]["text"] == "第一句"

    def test_save_subtitle_with_timestamps(self, tmp_path):
        """save_subtitle_as_transcript 保存带 start_ms/end_ms 的 segments。"""
        json_path = tmp_path / "transcript.json"
        txt_path = tmp_path / "transcript.txt"
        segments = [
            {"start_ms": 0, "end_ms": 2000, "text": "第一句"},
            {"start_ms": 2000, "end_ms": 4000, "text": "第二句"},
        ]
        seg_cache = tmp_path / "_subtitle_segments.json"
        seg_cache.write_text(json.dumps(segments, ensure_ascii=False), encoding="utf-8")
        vs_process.save_subtitle_as_transcript(
            "第一句\n第二句", json_path, txt_path, "zh", run_dir=tmp_path)
        data = json.loads(json_path.read_text("utf-8"))
        # 应保存为带 segments key 的 dict 格式
        segs = data if isinstance(data, list) else data.get("segments", [])
        assert len(segs) == 2
        assert segs[0].get("start_ms") == 0
        assert segs[0].get("end_ms") == 2000
