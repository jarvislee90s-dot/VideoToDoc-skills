from __future__ import annotations

import shutil
from pathlib import Path

from .align import align_sections
from .asr import transcribe_audio
from .audio import extract_audio, probe_duration_ms
from .config import Settings
from .document import (
    ensure_semantic_markdown,
    generate_mindmap,
    markdown_to_docx,
    render_compact_markdown,
    render_original_markdown,
)
from .io import read_json, write_json
from .models import ProcessResult, Section, Slide, SlideSet, to_plain_dict
from .mindmap import render_mindmap_and_refresh_docs
from .quality import write_quality_report
from .slides import (
    cross_segment_dedupe,
    deduplicate_slides,
    detect_slides,
    finalize_segment_slides,
    slides_from_dict,
    trim_candidates_by_transcript,
)
from .segment import capture_interval_for_duration, generate_pending_segments
from .sync import estimate_sync_offset_ms
from datetime import datetime
from .utils import ensure_file, file_md5, slugify


def _transcript_from_external(data: object, language: str) -> "Transcript":
    """从外部 transcript 构造，兼容 秒·float / 毫秒·int（卡点⑥根因）。"""
    from .models import Transcript, TranscriptSegment
    items = data if isinstance(data, list) else data.get("segments", [])  # type: ignore[union-attr]
    segs = [TranscriptSegment(
        start_ms=int(s["start_ms"]) if "start_ms" in s else int(round(float(s.get("start", 0)) * 1000)),
        end_ms=int(s["end_ms"]) if "end_ms" in s else int(round(float(s.get("end", 0)) * 1000)),
        text=s.get("text", ""),
    ) for s in items]
    return Transcript(backend="reused", language=language, segments=segs)


def capture_video(
    video_path: Path,
    runs_dir: Path,
    settings: Settings,
    force_rebuild: set[str] | None = None,
) -> dict:
    """capture 阶段：提取音频 + ASR + 时长密度截图 + 生成分段草案。"""
    ensure_file(video_path, "视频文件")
    force_rebuild = force_rebuild or set()

    slug = slugify(video_path.stem)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = runs_dir / f"{slug}_{ts}"
    cache_dir = run_dir / "cache"
    run_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    audio_profile = _audio_profile_name(settings)
    backend_slug = slugify(settings.asr_backend)
    model_slug = slugify(settings.asr_model)
    video_hash = file_md5(video_path)[:12]
    audio_path = cache_dir / f"{video_hash}_{audio_profile}.wav"
    transcript_path = cache_dir / f"{video_hash}_{backend_slug}_{model_slug}.transcript.json"

    # 时长密度函数决定截图间隔
    duration_ms = probe_duration_ms(video_path)
    duration_sec = duration_ms / 1000
    settings.fallback_interval_sec = capture_interval_for_duration(duration_sec)

    slides_slug = slugify(
        f"{settings.capture_mode}_{settings.scene_threshold}_{settings.hash_threshold}_"
        f"{settings.fallback_interval_sec}_{settings.keep_all_candidates}"
    )
    slides_dir = run_dir / f"slides_{slides_slug}"
    slides_path = cache_dir / f"{video_hash}_{slides_slug}.candidates.json"

    # 步骤 1-2：音频 + ASR
    audio = extract_audio(video_path, audio_path, settings, force=_stage_forced(force_rebuild, "audio"))
    if settings.transcript_path:
        tpath = Path(settings.transcript_path)
        merged_path = tpath.parent / "transcript_merged.json"
        source_path = merged_path if merged_path.exists() else tpath
        if merged_path.exists():
            print(f"  ♻️  使用已合并转录：{merged_path.name}")
        transcript = _transcript_from_external(read_json(source_path), settings.language)
        # 写入 cache 供 finalize 阶段读取
        write_json(transcript_path, to_plain_dict(transcript))
        print(f"  ♻️  复用已有转录（{len(transcript.segments)} 段）")
    else:
        transcript = transcribe_audio(audio, transcript_path, settings, force=_stage_forced(force_rebuild, "asr"))

    # 步骤 3：截图（skip_dedupe，只生成候选）
    candidates = detect_slides(video_path, slides_dir, slides_path, settings,
                               force=_stage_forced(force_rebuild, "slides"), skip_dedupe=True)

    # 步骤 4：生成分段草案
    pending = generate_pending_segments(candidates, transcript, duration_sec,
                                        max_segment_chars=settings.max_segment_chars,
                                        min_segment_chars=settings.min_segment_chars)
    pending["video_title"] = video_path.stem
    pending["video_path"] = str(video_path.resolve())
    pending_path = run_dir / "pending_segments.json"
    write_json(pending_path, pending)

    return {
        "run_dir": str(run_dir.resolve()),
        "pending_segments_path": str(pending_path.resolve()),
        "candidates_count": len(candidates.slides),
    }



def _apply_merge_extensions(segments: list[dict]) -> list[dict]:
    """将 merge 段的时间范围扩展到目标段。

    merge 段的 end_ms 设为目标段的新 end_ms，
    同时将 merge 段的 candidate_slide_ids 合并到目标段。
    """
    seg_map = {s["id"]: dict(s) for s in segments}
    for seg in segments:
        if seg.get("suggested_action") == "merge" and seg.get("merge_into") in seg_map:
            target = seg_map[seg["merge_into"]]
            target["end_ms"] = max(target["end_ms"], seg["end_ms"])
            target.setdefault("candidate_slide_ids", []).extend(
                seg.get("candidate_slide_ids", []))
    return list(seg_map.values())


def finalize_video(
    run_dir: Path,
    settings: Settings,
) -> dict:
    """finalize 阶段：按 confirmed_segments.json 去重 + 补图 + 生成产物。"""
    confirmed_path = run_dir / "confirmed_segments.json"
    if not confirmed_path.exists():
        raise SystemExit(
            f"❌ confirmed_segments.json 不存在：{confirmed_path}\n"
            f"   请先运行: videotodoc review-segments {run_dir}"
        )

    confirmed = read_json(confirmed_path)
    segments = confirmed.get("segments", [])
    if not segments:
        raise SystemExit("❌ confirmed_segments.json 无分段数据")

    # 扩展 merge 段的时间范围到目标段
    segments = _apply_merge_extensions(segments)

    video_path = Path(confirmed.get("video_path", ""))

    # 找候选图缓存
    cache_dir = run_dir / "cache"
    candidates_files = list(cache_dir.glob("*.candidates.json"))
    if not candidates_files:
        raise SystemExit("❌ 找不到候选图缓存，请重新运行 capture")
    candidates = slides_from_dict(read_json(candidates_files[0]))

    # 找 transcript 缓存
    transcript_files = list(cache_dir.glob("*.transcript.json"))
    if transcript_files:
        transcript = _transcript_from_external(read_json(transcript_files[0]), settings.language)
    else:
        raise SystemExit("❌ 找不到转录缓存，请重新运行 capture")

    # 按 confirmed 分段处理
    fill_dir = run_dir / "fill_slides"
    fill_dir.mkdir(parents=True, exist_ok=True)

    all_slides: list[list[Slide]] = []
    for seg in segments:
        if seg["suggested_action"] == "merge":
            continue  # 合并段跳过，内容归到 merge_into
        seg_slides = finalize_segment_slides(seg, candidates, video_path, fill_dir, settings)
        all_slides.append(seg_slides)

    # 跨段边界去重
    cross_segment_dedupe(all_slides, settings)

    # 物化截图
    selected_dir = run_dir / "selected_slides_finalized"
    selected_dir.mkdir(parents=True, exist_ok=True)
    global_index = 0
    flat_slides: list[Slide] = []
    for seg_slides in all_slides:
        for slide in seg_slides:
            global_index += 1
            target = selected_dir / f"{global_index:04d}.png"
            source = Path(slide.image_path)
            if source.exists():
                shutil.copy2(source, target)
            flat_slides.append(Slide(
                slide_index=global_index, image_path=str(target),
                start_ms=slide.start_ms, end_ms=slide.end_ms,
                capture_ms=slide.capture_ms, confidence=slide.confidence,
                hash=slide.hash, edge_density=slide.edge_density,
            ))

    slideset = SlideSet(slides=flat_slides)

    # 图文对齐
    sync_offset_ms = settings.sync_offset_ms or 0
    sections = align_sections(slideset, transcript, sync_offset_ms)

    # 生成产物
    slug = confirmed.get("video_title", run_dir.stem)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    markdown_path = run_dir / f"{slug}_讲义_{ts}.md"
    compact_markdown_path = run_dir / f"{slug}_讲义_紧凑版_{ts}.md"
    semantic_markdown_path = run_dir / f"{slug}_讲义_整理版_{ts}.md"
    docx_path = run_dir / f"{slug}_讲义_{ts}.docx"
    semantic_docx_path = run_dir / f"{slug}_讲义_整理版_{ts}.docx"
    mindmap_path = run_dir / f"{slug}_思维导图_{ts}.mmd"
    mindmap_image_path = run_dir / f"{slug}_思维导图_{ts}.png"

    mindmap = generate_mindmap(slug, sections, mindmap_path, settings)
    if not mindmap_image_path.exists():
        temp_mindmap = run_dir / "mindmap.mmd"
        if not temp_mindmap.exists():
            temp_mindmap.symlink_to(mindmap_path.name)
        render_mindmap_and_refresh_docs(run_dir, mindmap_path=mindmap_path, image_path=mindmap_image_path)

    mm_image = mindmap_image_path if mindmap_image_path.exists() else None
    render_original_markdown(slug, sections, markdown_path)
    render_compact_markdown(slug, sections, compact_markdown_path, mm_image)
    ensure_semantic_markdown(slug, sections, semantic_markdown_path, mm_image)
    markdown_to_docx(compact_markdown_path, docx_path)
    markdown_to_docx(semantic_markdown_path, semantic_docx_path)

    return {
        "run_dir": str(run_dir.resolve()),
        "selected_slides_count": len(flat_slides),
    }


def process_video(
    video_path: Path,
    runs_dir: Path,
    settings: Settings,
    force_rebuild: set[str] | None = None,
    run_dir: Path | None = None,
) -> ProcessResult:
    ensure_file(video_path, "视频文件")
    force_rebuild = force_rebuild or set()

    # slug/ts 仍用于后续产物文件名；run_dir 外部传入优先（复用 video-summary 目录）
    slug = slugify(video_path.stem)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if run_dir is not None:
        run_dir = run_dir.resolve()
    else:
        run_dir = runs_dir / f"{slug}_{ts}"
    cache_dir = run_dir / "cache"
    run_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    audio_profile = _audio_profile_name(settings)
    backend_slug = slugify(settings.asr_backend)
    model_slug = slugify(settings.asr_model)
    slides_slug = slugify(
        f"{settings.capture_mode}_{settings.scene_threshold}_{settings.hash_threshold}_"
        f"{settings.fallback_interval_sec}_{settings.keep_all_candidates}"
    )
    slides_dir = run_dir / f"slides_{slides_slug}"
    selected_slides_dir = run_dir / f"selected_slides_{slides_slug}"
    trimmed_dir = run_dir / f"trimmed_{slides_slug}"
    video_hash = file_md5(video_path)[:12]
    audio_path = cache_dir / f"{video_hash}_{audio_profile}.wav"
    transcript_path = cache_dir / f"{video_hash}_{backend_slug}_{model_slug}.transcript.json"
    slides_path = cache_dir / f"{video_hash}_{slides_slug}.slides.json"
    sections_path = cache_dir / f"{video_hash}_{slides_slug}_{settings.sync_offset_ms or 'auto'}.sections.json"
    # 产物命名：视频标题_讲义_时间戳
    mindmap_path = run_dir / f"{slug}_思维导图_{ts}.mmd"
    mindmap_image_path = run_dir / f"{slug}_思维导图_{ts}.png"
    markdown_path = run_dir / f"{slug}_讲义_{ts}.md"
    compact_markdown_path = run_dir / f"{slug}_讲义_紧凑版_{ts}.md"
    semantic_markdown_path = run_dir / f"{slug}_讲义_整理版_{ts}.md"
    docx_path = run_dir / f"{slug}_讲义_{ts}.docx"
    semantic_docx_path = run_dir / f"{slug}_讲义_整理版_{ts}.docx"
    quality_report_path = run_dir / f"{slug}_质量报告_{ts}.md"

    # 步骤 1：提取音频
    audio = extract_audio(video_path, audio_path, settings, force=_stage_forced(force_rebuild, "audio"))

    # 步骤 2：ASR 转录（必须在截图裁剪之前完成）
    if settings.transcript_path:
        tpath = Path(settings.transcript_path)
        merged_path = tpath.parent / "transcript_merged.json"
        source_path = merged_path if merged_path.exists() else tpath
        if merged_path.exists():
            print(f"  ♻️  使用已合并转录：{merged_path.name}")
        transcript = _transcript_from_external(read_json(source_path), settings.language)
        print(f"  ♻️  转录段数：{len(transcript.segments)}")
    else:
        transcript = transcribe_audio(audio, transcript_path, settings, force=_stage_forced(force_rebuild, "asr"))

    # 步骤 3：生成候选截图（skip_dedupe=True，只生成候选图不做去重）
    candidates = detect_slides(
        video_path, slides_dir, slides_path, settings,
        force=_stage_forced(force_rebuild, "slides"),
        skip_dedupe=True,
    )

    # 步骤 4：按 ASR 段裁剪候选图（同段多图只留最后一张）
    trimmed = trim_candidates_by_transcript(
        candidates, transcript, video_path, trimmed_dir, settings,
    )

    # 步骤 5：跨段图像/OCR 去重
    slides = deduplicate_slides(trimmed, settings)

    # 步骤 6：把入选截图复制到干净目录
    candidates_metadata = candidates.metadata  # 保留候选阶段元数据
    slides = materialize_selected_slides(slides, selected_slides_dir)
    slides.metadata["candidates_metadata"] = candidates_metadata
    write_json(slides_path, to_plain_dict(slides))

    # 步骤 7：图文对齐
    if sections_path.exists() and not _stage_forced(force_rebuild, "align"):
        sections = sections_from_dict(read_json(sections_path))
    else:
        sync_offset_ms = estimate_sync_offset_ms(audio, slides, transcript, settings)
        sections = align_sections(slides, transcript, sync_offset_ms)
        write_json(
            sections_path,
            {
                "sync_offset_ms": sync_offset_ms,
                "sections": [to_plain_dict(section) for section in sections],
            },
        )

    sync_offset_ms = int(read_json(sections_path).get("sync_offset_ms", 0))
    mindmap = generate_mindmap(video_path.stem, sections, mindmap_path, settings)

    # 步骤 8：渲染思维导图 PNG（必须在生成 Markdown/Word 之前）
    if not mindmap_image_path.exists() or _stage_forced(force_rebuild, "mindmap"):
        # 创建临时 symlink 让 render_mindmap_and_refresh_docs 找到文件
        temp_mindmap = run_dir / "mindmap.mmd"
        if not temp_mindmap.exists():
            temp_mindmap.symlink_to(mindmap_path.name)
        render_mindmap_and_refresh_docs(run_dir, mindmap_path=mindmap_path, image_path=mindmap_image_path)

    mm_image = mindmap_image_path if mindmap_image_path.exists() else None
    render_original_markdown(video_path.stem, sections, markdown_path)
    render_compact_markdown(
        video_path.stem,
        sections,
        compact_markdown_path,
        mm_image,
    )
    ensure_semantic_markdown(
        video_path.stem,
        sections,
        semantic_markdown_path,
        mm_image,
    )
    generated_docx = markdown_to_docx(compact_markdown_path, docx_path)
    generated_semantic_docx = markdown_to_docx(semantic_markdown_path, semantic_docx_path)
    write_quality_report(quality_report_path, transcript, slides, sections, sync_offset_ms)

    return ProcessResult(
        run_dir=run_dir,
        transcript_path=transcript_path,
        slides_path=slides_path,
        sections_path=sections_path,
        markdown_path=markdown_path,
        mindmap_path=mindmap_path,
        compact_markdown_path=compact_markdown_path,
        semantic_markdown_path=semantic_markdown_path,
        mindmap_image_path=mindmap_image_path if mindmap_image_path.exists() else None,
        docx_path=generated_docx,
        semantic_docx_path=generated_semantic_docx,
        quality_report_path=quality_report_path,
    )


def sections_from_dict(data: dict) -> list[Section]:
    return [Section(**item) for item in data.get("sections", [])]


def materialize_selected_slides(slides: SlideSet, output_dir: Path) -> SlideSet:
    """把最终入选截图复制到干净目录。

    检测阶段为了保留"后一张重复页"可能留下未被引用的中间图片。这里不删除
    任何旧文件，只复制最终 JSON 里真正使用的图片，避免用户查看目录时误把
    中间图当成最终截图。
    """

    output_dir.mkdir(parents=True, exist_ok=True)
    for index, slide in enumerate(slides.slides, start=1):
        source = Path(slide.image_path)
        target = output_dir / f"{index:04d}{source.suffix or '.png'}"
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
        slide.slide_index = index
        slide.image_path = str(target)
    slides.metadata["selected_slides_dir"] = str(output_dir)
    return slides


def _audio_profile_name(settings: Settings) -> str:
    if settings.audio_profile != "auto":
        return settings.audio_profile
    if settings.asr_backend.lower().startswith("qwen"):
        return "source"
    return "16k_mono"


def _stage_forced(force_rebuild: set[str], stage: str) -> bool:
    return "all" in force_rebuild or stage in force_rebuild
