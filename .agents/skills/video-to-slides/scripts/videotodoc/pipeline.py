from __future__ import annotations

import re
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .align import align_sections
from .asr import transcribe_audio
from .audio import extract_audio, probe_duration_ms
from .config import Settings
from .document import (
    ensure_semantic_markdown,
    render_compact_markdown,
    render_original_markdown,
)
from .io import read_json, write_json
from .models import ProcessResult, Section, Slide, SlideSet, to_plain_dict
from .quality import write_quality_report
from .slides import (
    classify_video,
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
from .utils import VideoToDocError, ensure_file, file_md5, slugify, seconds_to_ms


def _title_from_run_dir(run_dir: Path) -> str | None:
    """从复用的 run_dir 名推断视频标题，去掉时间戳后缀。"""
    stem = run_dir.name
    m = re.search(r"(.+)_\d{8}_\d{6}$", stem)
    if m:
        return m.group(1)
    return stem


def _transcript_from_external(data: object, language: str) -> "Transcript":
    """从外部 transcript 构造，兼容 秒·float / 毫秒·int（卡点⑥根因）。"""
    from .models import Transcript, TranscriptSegment
    items = data if isinstance(data, list) else data.get("segments", [])  # type: ignore[union-attr]
    segs = [TranscriptSegment(
        start_ms=int(s["start_ms"]) if "start_ms" in s else seconds_to_ms(float(s.get("start", 0))),
        end_ms=int(s["end_ms"]) if "end_ms" in s else seconds_to_ms(float(s.get("end", 0))),
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

    # auto 时自动判定视频类型
    if settings.video_type == "auto":
        settings.video_type = classify_video(video_path)

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

    # 步骤 1：提取音频
    audio = extract_audio(video_path, audio_path, settings, force=_stage_forced(force_rebuild, "audio"))

    # 步骤 2-3 并行：ASR 转录 + 截图检测（skip_dedupe）
    if settings.transcript_path:
        tpath = Path(settings.transcript_path)
        merged_path = tpath.parent / "transcript_merged.json"
        source_path = merged_path if merged_path.exists() else tpath
        if merged_path.exists():
            print(f"  ♻️  使用已合并转录：{merged_path.name}")
        transcript = _transcript_from_external(read_json(source_path), settings.language)
        write_json(transcript_path, to_plain_dict(transcript))
        print(f"  ♻️  复用已有转录（{len(transcript.segments)} 段）")
        candidates = detect_slides(video_path, slides_dir, slides_path, settings,
                                   force=_stage_forced(force_rebuild, "slides"), skip_dedupe=True)
    else:
        def _run_asr():
            return transcribe_audio(audio, transcript_path, settings, force=_stage_forced(force_rebuild, "asr"))
        def _run_detect():
            return detect_slides(video_path, slides_dir, slides_path, settings,
                                 force=_stage_forced(force_rebuild, "slides"), skip_dedupe=True)
        with ThreadPoolExecutor(max_workers=2) as executor:
            f_asr = executor.submit(_run_asr)
            f_detect = executor.submit(_run_detect)
            transcript = f_asr.result()
            candidates = f_detect.result()

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


def _find_matching_cache_file(
    files: list[Path],
    video_path: Path,
    label: str,
) -> Path:
    """在 cache 文件列表中按 video_hash 匹配对应文件。

    匹配策略（按优先级）：
    1. 文件名以 video_hash 前12位开头（capture_video 命名规范）
    2. JSON 顶层 video_hash 字段等于完整 md5
    3. JSON metadata.video_hash 字段等于完整 md5
    4. 仅一个文件时兜底使用（向后兼容）
    5. 多文件无匹配时抛出 VideoToDocError
    """
    if not files:
        raise VideoToDocError(f"❌ 找不到{label}缓存，请重新运行 capture")

    video_hash_full = file_md5(video_path)
    video_hash_short = video_hash_full[:12]

    for cf in files:
        if cf.name.startswith(f"{video_hash_short}_"):
            return cf

    for cf in files:
        try:
            data = read_json(cf)
        except Exception:
            continue
        if isinstance(data, dict):
            if data.get("video_hash") == video_hash_full:
                return cf
            meta = data.get("metadata", {})
            if isinstance(meta, dict) and meta.get("video_hash") == video_hash_full:
                return cf

    if len(files) == 1:
        return files[0]

    raise VideoToDocError(
        f"❌ cache 目录无匹配 video_hash 的{label}文件，请重跑 capture"
    )


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

    # 找候选图缓存（按 video_hash 匹配，防止错配）
    cache_dir = run_dir / "cache"
    candidates_files = list(cache_dir.glob("*.candidates.json"))
    matched_candidates = _find_matching_cache_file(candidates_files, video_path, "候选图")
    candidates = slides_from_dict(read_json(matched_candidates))

    # 优先用阶段 0 产出的 review-passed merged（agent 已在阶段 0 末尾跑过 check_review_report.py）
    run_dir_merged = run_dir / "transcript_merged.json"
    if run_dir_merged.exists():
        transcript = _transcript_from_external(read_json(run_dir_merged), settings.language)
        print(f"  ♻️  finalize 使用 review-passed merged：{run_dir_merged.name}")
    else:
        # 找 transcript 缓存（按 video_hash 匹配）
        transcript_files = list(cache_dir.glob("*.transcript.json"))
        matched_transcript = _find_matching_cache_file(transcript_files, video_path, "转录")
        transcript = _transcript_from_external(read_json(matched_transcript), settings.language)

    # 按 confirmed 分段处理
    fill_dir = run_dir / "fill_slides"
    fill_dir.mkdir(parents=True, exist_ok=True)

    seg_tasks: list[tuple[int, dict]] = []
    for seg_idx, seg in enumerate(segments):
        if seg["suggested_action"] == "merge":
            continue
        seg_tasks.append((seg_idx, seg))

    all_slides_by_idx: dict[int, list[Slide]] = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        def _finalize_seg(task: tuple[int, dict]) -> tuple[int, list[Slide]]:
            idx, seg = task
            result = finalize_segment_slides(seg, candidates, video_path, fill_dir, settings)
            return (idx, result)
        futures = {executor.submit(_finalize_seg, t): t[0] for t in seg_tasks}
        for future in as_completed(futures):
            idx, seg_slides = future.result()
            all_slides_by_idx[idx] = seg_slides

    all_slides: list[list[Slide]] = []
    for seg_idx, seg in enumerate(segments):
        if seg["suggested_action"] == "merge":
            continue
        all_slides.append(all_slides_by_idx[seg_idx])

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

    # 生成产物（仅 Markdown，思维导图与 Word 在 Agent 整理后由 render_mindmap.py 生成）
    # 优先使用 confirmed_segments.json 中的 video_title；若缺失则从 run_dir 名推断，
    # 确保复用 video-summary 目录时产物名与 Markdown 标题一致
    title = confirmed.get("video_title") or _title_from_run_dir(run_dir)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    markdown_path = run_dir / f"{title}_讲义_{ts}.md"
    compact_markdown_path = run_dir / f"{title}_讲义_紧凑版_{ts}.md"
    semantic_markdown_path = run_dir / f"{title}_讲义_整理版_{ts}.md"

    def _render_original_md():
        render_original_markdown(title, sections, markdown_path)

    with ThreadPoolExecutor(max_workers=1) as executor:
        f_orig_md = executor.submit(_render_original_md)
        f_orig_md.result()

    def _render_compact_md():
        render_compact_markdown(title, sections, compact_markdown_path, mindmap_image_path=None)

    def _render_semantic_md():
        ensure_semantic_markdown(title, sections, semantic_markdown_path, mindmap_image_path=None)

    with ThreadPoolExecutor(max_workers=2) as executor:
        f_compact = executor.submit(_render_compact_md)
        f_semantic = executor.submit(_render_semantic_md)
        f_compact.result()
        f_semantic.result()

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

    # auto 时自动判定视频类型（影响 detect_slides 场景阈值 + trim 段末取帧策略）
    if settings.video_type == "auto":
        settings.video_type = classify_video(video_path)

    # run_dir 外部传入时（复用 video-summary 目录），优先从 run_dir 名推断标题
    if run_dir is not None:
        run_dir = run_dir.resolve()
        title = _title_from_run_dir(run_dir)
    else:
        title = None

    # 外部 run_dir 复用时，产物文件名和 Markdown 标题使用原始标题；新建 run_dir 时仍用 slug 保证文件系统安全
    file_title = title if run_dir is not None else slugify(title or video_path.stem)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if run_dir is None:
        run_dir = runs_dir / f"{slugify(title or video_path.stem)}_{ts}"
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
    # 产物命名：仅 Markdown，思维导图与 Word 在 Agent 整理后生成
    markdown_path = run_dir / f"{file_title}_讲义_{ts}.md"
    compact_markdown_path = run_dir / f"{file_title}_讲义_紧凑版_{ts}.md"
    semantic_markdown_path = run_dir / f"{file_title}_讲义_整理版_{ts}.md"
    quality_report_path = run_dir / f"{file_title}_质量报告_{ts}.md"

    # 步骤 1：提取音频
    audio = extract_audio(video_path, audio_path, settings, force=_stage_forced(force_rebuild, "audio"))

    # 步骤 2-3 并行：ASR 转录 + 候选截图检测
    if settings.transcript_path:
        tpath = Path(settings.transcript_path)
        merged_path = tpath.parent / "transcript_merged.json"
        source_path = merged_path if merged_path.exists() else tpath
        if merged_path.exists():
            print(f"  ♻️  使用已合并转录：{merged_path.name}")
        transcript = _transcript_from_external(read_json(source_path), settings.language)
        print(f"  ♻️  转录段数：{len(transcript.segments)}")
        candidates = detect_slides(
            video_path, slides_dir, slides_path, settings,
            force=_stage_forced(force_rebuild, "slides"),
            skip_dedupe=True,
        )
    else:
        def _run_asr_pv():
            return transcribe_audio(audio, transcript_path, settings, force=_stage_forced(force_rebuild, "asr"))
        def _run_detect_pv():
            return detect_slides(
                video_path, slides_dir, slides_path, settings,
                force=_stage_forced(force_rebuild, "slides"),
                skip_dedupe=True,
            )
        with ThreadPoolExecutor(max_workers=2) as executor:
            f_asr_pv = executor.submit(_run_asr_pv)
            f_detect_pv = executor.submit(_run_detect_pv)
            transcript = f_asr_pv.result()
            candidates = f_detect_pv.result()

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
        sections_data = read_json(sections_path)
        sections = sections_from_dict(sections_data)
        sync_offset_ms = int(sections_data.get("sync_offset_ms", 0))
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

    def _render_original_md_pv():
        # 统一使用 file_title（来自 run_dir 标题），避免 video_path.stem 导致标题变成 "video"
        render_original_markdown(file_title, sections, markdown_path)

    def _write_quality_report_pv():
        write_quality_report(quality_report_path, transcript, slides, sections, sync_offset_ms)

    with ThreadPoolExecutor(max_workers=2) as executor:
        f_orig_md_pv = executor.submit(_render_original_md_pv)
        f_quality_pv = executor.submit(_write_quality_report_pv)
        f_orig_md_pv.result()
        f_quality_pv.result()

    def _render_compact_md_pv():
        render_compact_markdown(
            file_title,
            sections,
            compact_markdown_path,
            mindmap_image_path=None,
        )

    def _render_semantic_md_pv():
        ensure_semantic_markdown(
            file_title,
            sections,
            semantic_markdown_path,
            mindmap_image_path=None,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        f_compact_pv = executor.submit(_render_compact_md_pv)
        f_semantic_pv = executor.submit(_render_semantic_md_pv)
        f_compact_pv.result()
        f_semantic_pv.result()

    return ProcessResult(
        run_dir=run_dir,
        transcript_path=transcript_path,
        slides_path=slides_path,
        sections_path=sections_path,
        markdown_path=markdown_path,
        mindmap_path=None,
        compact_markdown_path=compact_markdown_path,
        semantic_markdown_path=semantic_markdown_path,
        mindmap_image_path=None,
        mindmap_image_paths=[],
        docx_path=None,
        semantic_docx_path=None,
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
    semantic_pattern = re.compile(r"^p\d{2}_\d{2}(?:_main|_cand)?_\d+\.\d+s\.png$")
    for index, slide in enumerate(slides.slides, start=1):
        source = Path(slide.image_path)
        # 保留 trim 阶段生成的语义命名（spec 4.6），否则用顺序编号
        if semantic_pattern.match(source.name):
            target = output_dir / source.name
        else:
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
