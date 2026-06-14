from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import Settings, load_config
from .mindmap import render_mindmap_and_refresh_docs
from .pipeline import process_video
from .utils import VideoToDocError


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "process":
            return _process(args)
        if args.command == "render-mindmap":
            return _render_mindmap(args)
        parser.print_help()
        return 1
    except VideoToDocError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="videotodoc", description="课程视频转图文讲义")
    subparsers = parser.add_subparsers(dest="command")

    process = subparsers.add_parser("process", help="处理视频并生成本地讲义产物")
    process.add_argument("video", type=Path)
    process.add_argument("--config", type=Path, default=Path("config.yaml"))
    process.add_argument("--runs-dir", type=Path, default=Path("runs"))
    process.add_argument("--asr", dest="asr_backend")
    process.add_argument("--model", dest="asr_model")
    process.add_argument("--language")
    process.add_argument("--scene-threshold", type=float)
    process.add_argument("--hash-threshold", type=int)
    process.add_argument("--capture-mode", choices=["fast", "fine", "audit", "complete"])
    process.add_argument("--fallback-interval-sec", type=int)
    process.add_argument("--keep-all-candidates", action="store_true")
    process.add_argument("--ocr-dedupe", action="store_true")
    process.add_argument("--ocr-similarity-threshold", type=float)
    process.add_argument("--duplicate-change-threshold", type=float)
    process.add_argument("--different-change-threshold", type=float)
    process.add_argument("--different-hash-threshold", type=int)
    process.add_argument("--sync-offset-ms", type=int)
    process.add_argument("--force-rebuild", action="append", default=[], help="可重复传入：audio/asr/slides/align/all")

    mindmap = subparsers.add_parser("render-mindmap", help="渲染 mindmap.mmd 并刷新 Word")
    mindmap.add_argument("run_dir", type=Path)

    return parser


def _process(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    result = process_video(args.video, args.runs_dir, settings, set(args.force_rebuild))
    print("处理完成：")
    print(f"- run_dir: {result.run_dir}")
    print(f"- transcript: {result.transcript_path}")
    print(f"- slides: {result.slides_path}")
    print(f"- sections: {result.sections_path}")
    print(f"- markdown: {result.markdown_path}")
    if result.compact_markdown_path:
        print(f"- compact_markdown: {result.compact_markdown_path}")
    if result.semantic_markdown_path:
        print(f"- semantic_markdown: {result.semantic_markdown_path}")
    print(f"- mindmap: {result.mindmap_path}")
    if result.mindmap_image_path:
        print(f"- mindmap_image: {result.mindmap_image_path}")
    if result.docx_path:
        print(f"- docx: {result.docx_path}")
    if result.semantic_docx_path:
        print(f"- semantic_docx: {result.semantic_docx_path}")
    if result.quality_report_path:
        print(f"- quality_report: {result.quality_report_path}")
    return 0


def _render_mindmap(args: argparse.Namespace) -> int:
    image_path, refreshed = render_mindmap_and_refresh_docs(args.run_dir)
    print("思维导图已渲染：")
    print(f"- image: {image_path}")
    for docx_path in refreshed:
        print(f"- refreshed_docx: {docx_path}")
    return 0


def _settings_from_args(args: argparse.Namespace) -> Settings:
    settings = load_config(args.config)
    for field in (
        "asr_backend",
        "asr_model",
        "language",
        "scene_threshold",
        "hash_threshold",
        "capture_mode",
        "fallback_interval_sec",
        "ocr_similarity_threshold",
        "duplicate_change_threshold",
        "different_change_threshold",
        "different_hash_threshold",
        "sync_offset_ms",
    ):
        value = getattr(args, field, None)
        if value is not None:
            setattr(settings, field, value)
    if getattr(args, "keep_all_candidates", False):
        settings.keep_all_candidates = True
    if getattr(args, "ocr_dedupe", False):
        settings.ocr_dedupe = True
    return settings


if __name__ == "__main__":
    raise SystemExit(main())
