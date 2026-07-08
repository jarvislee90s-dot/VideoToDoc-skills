"""测试 process.py 的 transcript.json 输出格式统一性。

ASR 路径与字幕路径都必须产出 dict+毫秒+backend 字段的 schema，
保证下游 video-to-slides 可一致读取。
"""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# 把 scripts/ 加到 sys.path 以便导入 process
SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import process  # noqa: E402


def test_transcribe_audio_outputs_dict_with_milliseconds(tmp_path: Path) -> None:
    """ASR 路径应产出 {segments:[{start_ms,end_ms,text}], language, backend} 顶层 dict。"""
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"")  # 存在即可，内容不参与转录

    fake_segments = [
        {"start": 0.0, "end": 1.16, "text": "你好"},
        {"start": 1.16, "end": 2.62, "text": "世界"},
    ]
    fake_result = {"segments": fake_segments, "language": "zh"}

    # mlx_whisper 在 transcribe_audio 内 import，需先在 sys.modules 注册
    fake_mlx = MagicMock()
    fake_mlx.transcribe.return_value = fake_result

    with patch.dict(sys.modules, {"mlx_whisper": fake_mlx}):
        process.transcribe_audio(audio, tmp_path, model="fake-model", language="zh")

    out = json.loads((tmp_path / "transcript.json").read_text(encoding="utf-8"))

    assert isinstance(out, dict), f"顶层必须是 dict，实际是 {type(out).__name__}"
    assert set(out.keys()) >= {"segments", "language", "backend"}
    assert out["language"] == "zh"
    assert out["backend"] == "mlx-whisper"

    segs = out["segments"]
    assert isinstance(segs, list)
    assert len(segs) == 2

    first = segs[0]
    assert set(first.keys()) == {"start_ms", "end_ms", "text"}
    assert first["start_ms"] == 0
    assert first["end_ms"] == 1160
    assert first["text"] == "你好"
    assert isinstance(first["start_ms"], int)
    assert isinstance(first["end_ms"], int)

    second = segs[1]
    assert second["start_ms"] == 1160
    assert second["end_ms"] == 2620
    assert second["text"] == "世界"


def test_transcribe_audio_skips_when_transcript_exists(tmp_path: Path) -> None:
    """transcript.json + transcript.txt 都存在时应直接跳过，不调用 mlx_whisper。"""
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"")
    (tmp_path / "transcript.json").write_text(
        json.dumps({"segments": [], "language": "zh", "backend": "mlx-whisper"}),
        encoding="utf-8",
    )
    (tmp_path / "transcript.txt").write_text("", encoding="utf-8")

    fake_mlx = MagicMock()
    with patch.dict(sys.modules, {"mlx_whisper": fake_mlx}):
        process.transcribe_audio(audio, tmp_path, model="fake-model", language="zh")

    fake_mlx.transcribe.assert_not_called()


def test_save_subtitle_as_transcript_includes_backend(tmp_path: Path) -> None:
    """字幕路径产物的 dict 顶层必须包含 backend 字段，值为 'subtitle'。"""
    json_path = tmp_path / "transcript.json"
    txt_path = tmp_path / "transcript.txt"

    process.save_subtitle_as_transcript(
        "第一行\n第二行\n",
        json_path,
        txt_path,
        language="zh",
        run_dir=tmp_path,
    )

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert "backend" in data
    assert data["backend"] == "subtitle"
    assert data["language"] == "zh"
    assert isinstance(data["segments"], list)
    assert all(
        set(seg.keys()) == {"start_ms", "end_ms", "text"} for seg in data["segments"]
    )


def test_transcribe_and_subtitle_share_schema(tmp_path: Path) -> None:
    """ASR 路径与字幕路径产出的顶层 key 集合必须一致（仅 backend 值不同）。"""
    # 字幕路径
    sub_json = tmp_path / "sub.json"
    sub_txt = tmp_path / "sub.txt"
    process.save_subtitle_as_transcript(
        "x", sub_json, sub_txt, language="zh", run_dir=tmp_path
    )
    sub_keys = set(json.loads(sub_json.read_text(encoding="utf-8")).keys())

    # ASR 路径
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"")
    asr_dir = tmp_path / "asr"
    asr_dir.mkdir()
    fake_mlx = MagicMock()
    fake_mlx.transcribe.return_value = {
        "segments": [{"start": 0.0, "end": 1.0, "text": "x"}],
        "language": "zh",
    }
    with patch.dict(sys.modules, {"mlx_whisper": fake_mlx}):
        process.transcribe_audio(audio, asr_dir, model="fake", language="zh")
    asr_keys = set(json.loads((asr_dir / "transcript.json").read_text(encoding="utf-8")).keys())

    assert sub_keys == asr_keys
