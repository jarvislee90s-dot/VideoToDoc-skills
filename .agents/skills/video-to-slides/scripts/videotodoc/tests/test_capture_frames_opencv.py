"""opencv 批量截图测试（任务 7）。"""

import cv2
import numpy as np
from pathlib import Path


def _create_test_video(path: Path, duration_sec: float = 5.0, fps: int = 10) -> None:
    """用 opencv 创建一个测试视频。"""
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, fps, (64, 64))
    total_frames = int(duration_sec * fps)
    for i in range(total_frames):
        frame = np.full((64, 64, 3), i % 256, dtype=np.uint8)
        writer.write(frame)
    writer.release()


def test_capture_frames_opencv_returns_dict(tmp_path: Path) -> None:
    from videotodoc.slides import capture_frames_opencv
    video = tmp_path / "test.mp4"
    _create_test_video(video, duration_sec=3.0)
    out_dir = tmp_path / "frames"
    timestamps = [500, 1500, 2500]  # ms
    results = capture_frames_opencv(video, timestamps, out_dir)
    assert len(results) == 3
    for ms in timestamps:
        assert ms in results
        assert results[ms].exists()
        assert results[ms].suffix == ".png"


def test_capture_frames_opencv_handles_missing_timestamp(tmp_path: Path) -> None:
    from videotodoc.slides import capture_frames_opencv
    video = tmp_path / "test.mp4"
    _create_test_video(video, duration_sec=2.0)
    out_dir = tmp_path / "frames"
    # 时间戳超过视频时长，返回空（不抛异常）
    results = capture_frames_opencv(video, [5000], out_dir)
    assert isinstance(results, dict)
    assert 5000 not in results


def test_capture_frames_opencv_custom_template(tmp_path: Path) -> None:
    from videotodoc.slides import capture_frames_opencv
    video = tmp_path / "test.mp4"
    _create_test_video(video, duration_sec=2.0)
    out_dir = tmp_path / "frames"
    timestamps = [500, 1000]
    results = capture_frames_opencv(
        video, timestamps, out_dir, name_template="frame_{ms:07d}.png"
    )
    assert (out_dir / "frame_0000500.png").exists()
    assert (out_dir / "frame_0001000.png").exists()
