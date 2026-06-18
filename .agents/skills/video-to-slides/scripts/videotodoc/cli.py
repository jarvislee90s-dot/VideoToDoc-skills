from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import Settings, load_config
from .mindmap import render_mindmap_and_refresh_docs
from .pipeline import capture_video, finalize_video, process_video
from .utils import VideoToDocError


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "capture":
            return _capture(args)
        if args.command == "review-segments":
            return _review_segments(args)
        if args.command == "finalize":
            return _finalize(args)
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
    process.add_argument("--no-ocr-dedupe", action="store_true",
                         help="关闭 OCR 辅助去重（白底 PPT 易误合并，不建议）")
    process.add_argument("--ocr-similarity-threshold", type=float)
    process.add_argument("--duplicate-change-threshold", type=float)
    process.add_argument("--different-change-threshold", type=float)
    process.add_argument("--different-hash-threshold", type=int)
    process.add_argument("--sync-offset-ms", type=int)
    process.add_argument("--force-rebuild", action="append", default=[], help="可重复传入：audio/asr/slides/align/all")
    process.add_argument("--transcript", type=Path, default=None,
                         help="已有转录文件路径（跳过 ASR）")

    capture = subparsers.add_parser("capture", help="截图 + ASR + 生成分段草案")
    capture.add_argument("video", type=Path)
    capture.add_argument("--runs-dir", type=Path, default=Path("runs"))
    capture.add_argument("--asr", dest="asr_backend")
    capture.add_argument("--model", dest="asr_model")
    capture.add_argument("--language")
    capture.add_argument("--transcript", type=Path, default=None, help="已有转录文件路径")
    capture.add_argument("--capture-mode", choices=["fast", "fine", "audit", "complete"])
    capture.add_argument("--force-rebuild", action="append", default=[])

    review = subparsers.add_parser("review-segments", help="审查分段草案，校验 confirmed 格式")
    review.add_argument("run_dir", type=Path)
    review.add_argument("--confirmed", type=Path, default=None,
                        help="confirmed_segments.json 路径（默认 run_dir/confirmed_segments.json）")

    finalize = subparsers.add_parser("finalize", help="按 confirmed 分段去重补图 + 生成产物")
    finalize.add_argument("run_dir", type=Path)
    finalize.add_argument("--capture-mode", choices=["fast", "fine", "audit", "complete"])
    finalize.add_argument("--no-ocr-dedupe", action="store_true",
                          help="关闭 OCR 辅助去重（白底 PPT 易误合并，不建议）")
    finalize.add_argument("--force-rebuild", action="append", default=[])

    mindmap = subparsers.add_parser("render-mindmap", help="渲染 mindmap.mmd 并刷新 Word")
    mindmap.add_argument("run_dir", type=Path)

    return parser


def _review_segments(args: argparse.Namespace) -> int:
    from .segment import validate_confirmed_segments
    from .io import read_json

    pending_path = args.run_dir / "pending_segments.json"
    if not pending_path.exists():
        print(f"❌ 分段草案不存在：{pending_path}", file=sys.stderr)
        print("请先运行: videotodoc capture <video>", file=sys.stderr)
        return 2

    pending = read_json(pending_path)
    print("📋 分段草案（pending_segments.json）")
    print(f"   视频时长：{pending.get('duration_sec', '?')}s")
    print(f"   截图间隔：{pending.get('capture_interval_sec', '?')}s")
    print(f"   分段数：{len(pending.get('segments', []))}")
    print()
    for seg in pending.get("segments", []):
        action = seg["suggested_action"]
        merge_info = f" → {seg.get('merge_into', '')}" if action == "merge" else ""
        print(f"  {seg['id']} [{action}{merge_info}] {seg['start_ms']//1000}s-{seg['end_ms']//1000}s "
              f"({seg.get('char_count', '?')}字) {seg['label']}")

    confirmed_path = args.confirmed or (args.run_dir / "confirmed_segments.json")
    if confirmed_path.exists():
        confirmed = read_json(confirmed_path)
        if validate_confirmed_segments(confirmed):
            print(f"\n✅ confirmed_segments.json 格式校验通过：{confirmed_path}")
            print("请运行: videotodoc finalize <run_dir>")
            return 0
        else:
            print(f"\n❌ confirmed_segments.json 格式校验失败，请检查", file=sys.stderr)
            return 1
    else:
        print(f"\n📝 请编辑分段草案后保存为：{confirmed_path}")
        print("   修改 suggested_action（keep/merge/split），merge 需带 merge_into，split 需带 split_at")
        return 0


def _finalize(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    result = finalize_video(args.run_dir, settings)
    print("FINALIZE_DONE")
    print(f"- run_dir: {result['run_dir']}")
    print(f"- selected_slides_count: {result['selected_slides_count']}")
    return 0


def _capture(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    if getattr(args, "transcript", None):
        settings.transcript_path = str(args.transcript)
    result = capture_video(args.video, args.runs_dir, settings, set(args.force_rebuild))
    print("CAPTURE_DONE")
    print(f"- run_dir: {result['run_dir']}")
    print(f"- pending_segments: {result['pending_segments_path']}")
    print(f"- candidates: {result['candidates_count']}")
    print("请 agent 审查分段草案后运行: videotodoc review-segments <run_dir>")
    return 0


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
    config_path = getattr(args, "config", None) or Path("config.yaml")
    settings = load_config(config_path)
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
    if getattr(args, "no_ocr_dedupe", False):
        settings.ocr_dedupe = False
    transcript_path = getattr(args, "transcript", None)
    if transcript_path:
        settings.transcript_path = str(transcript_path)
    return settings


if __name__ == "__main__":
    raise SystemExit(main())
