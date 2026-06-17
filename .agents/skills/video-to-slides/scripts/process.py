#!/usr/bin/env python3
"""Video-to-Slides Skill 入口：在已有视频+音频+字幕的前提下，截图去重→图文对齐→语义整理→Word。"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from _project import find_project_dir, project_python


def main() -> int:
    parser = argparse.ArgumentParser(
        description="视频截图→图文对齐→语义整理→Word。缺少前置产物时提示运行 video-summary。"
    )
    parser.add_argument("video", type=Path, help="视频文件路径")
    parser.add_argument("--project-dir", type=Path, default=None, help="VideoToDoc 项目根目录（默认自动检测）")
    parser.add_argument("--asr", default="mlx-whisper", help="ASR 后端（默认 mlx-whisper）")
    parser.add_argument("--model", default=None, help="ASR 模型名称")
    parser.add_argument("--transcript", type=Path, default=None, help="已有转录文件路径（跳过 ASR）")
    parser.add_argument("--capture-mode", choices=["fast", "fine", "audit", "complete"], default="audit")
    parser.add_argument("--scene-threshold", type=float, default=None)
    parser.add_argument("--fallback-interval-sec", type=int, default=15)
    parser.add_argument("--hash-threshold", type=int, default=None)
    parser.add_argument("--keep-all-candidates", action="store_true")
    parser.add_argument("--ocr-dedupe", action="store_true")
    parser.add_argument("--ocr-similarity-threshold", type=float, default=None)
    parser.add_argument("--duplicate-change-threshold", type=float, default=None)
    parser.add_argument("--different-change-threshold", type=float, default=None)
    parser.add_argument("--different-hash-threshold", type=int, default=None)
    parser.add_argument("--sync-offset-ms", type=int, default=None)
    parser.add_argument("--force-rebuild", action="append", default=[], help="可重复传入：audio/asr/slides/align/all")
    args = parser.parse_args()

    video_path = args.video.expanduser().resolve()
    if not video_path.exists():
        print(f"❌ 视频不存在：{video_path}", file=sys.stderr)
        print(f"   如果视频是网页链接，请先运行 video-summary Skill 下载：")
        print(f"   python3 skills/video-summary/scripts/process.py '<视频URL>'")
        return 2

    project_dir = find_project_dir(args.project_dir, video_path)
    python_bin = project_python(project_dir)

    # 基础命令
    cmd = [
        str(python_bin), "-m", "videotodoc.cli", "process",
        str(video_path), "--asr", args.asr, "--capture-mode", args.capture_mode,
    ]

    # 可选参数
    if args.model:
        cmd += ["--model", args.model]
    if args.scene_threshold is not None:
        cmd += ["--scene-threshold", str(args.scene_threshold)]
    if args.fallback_interval_sec is not None:
        cmd += ["--fallback-interval-sec", str(args.fallback_interval_sec)]
    if args.hash_threshold is not None:
        cmd += ["--hash-threshold", str(args.hash_threshold)]
    if args.keep_all_candidates:
        cmd.append("--keep-all-candidates")
    if args.ocr_dedupe:
        cmd.append("--ocr-dedupe")
    if args.ocr_similarity_threshold is not None:
        cmd += ["--ocr-similarity-threshold", str(args.ocr_similarity_threshold)]
    if args.duplicate_change_threshold is not None:
        cmd += ["--duplicate-change-threshold", str(args.duplicate_change_threshold)]
    if args.different_change_threshold is not None:
        cmd += ["--different-change-threshold", str(args.different_change_threshold)]
    if args.different_hash_threshold is not None:
        cmd += ["--different-hash-threshold", str(args.different_hash_threshold)]
    if args.sync_offset_ms is not None:
        cmd += ["--sync-offset-ms", str(args.sync_offset_ms)]
    for target in args.force_rebuild:
        cmd += ["--force-rebuild", target]

    print(f"🚀 运行 VideoToDoc 流程...")
    print(f"   视频：{video_path.name}")
    print(f"   ASR：{args.asr}")
    print(f"   截图模式：{args.capture_mode}")
    if args.ocr_dedupe:
        print(f"   OCR 去重：开启")

    result = subprocess.run(
        cmd, cwd=project_dir,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parent)},
        text=True, stdout=sys.stdout, stderr=sys.stderr,
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
