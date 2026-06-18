from __future__ import annotations

import shutil
from pathlib import Path

from .align import align_sections
from .asr import transcribe_audio
from .audio import extract_audio
from .config import Settings
from .document import (
    ensure_semantic_markdown,
    generate_mindmap,
    markdown_to_docx,
    render_compact_markdown,
    render_original_markdown,
)
from .io import read_json, write_json
from .models import ProcessResult, Section, SlideSet, to_plain_dict
from .mindmap import render_mindmap_and_refresh_docs
from .quality import write_quality_report
from .slides import deduplicate_slides, detect_slides, trim_candidates_by_transcript
from .sync import estimate_sync_offset_ms
from datetime import datetime
from .utils import ensure_file, file_md5, slugify


def process_video(
    video_path: Path,
    runs_dir: Path,
    settings: Settings,
    force_rebuild: set[str] | None = None,
) -> ProcessResult:
    ensure_file(video_path, "视频文件")
    force_rebuild = force_rebuild or set()

    # 使用视频标题+时间戳命名 run 目录
    slug = slugify(video_path.stem)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
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
        from .io import read_json
        from .models import Transcript, TranscriptSegment
        data = read_json(Path(settings.transcript_path))
        segs = [TranscriptSegment(start_ms=s.get("start_ms", s.get("start", 0)),
                                  end_ms=s.get("end_ms", s.get("end", 0)),
                                  text=s.get("text", ""))
                for s in (data if isinstance(data, list) else data.get("segments", []))]
        transcript = Transcript(backend="reused", language=settings.language, segments=segs)
        print(f"  ♻️  复用已有转录：{settings.transcript_path}（{len(segs)} 段）")
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
