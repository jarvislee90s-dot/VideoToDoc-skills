from __future__ import annotations

import math
import re
import shutil
import tempfile
from pathlib import Path

from PIL import Image, ImageFilter
from PIL import ImageChops

from .audio import probe_duration_ms
from .config import Settings
from .io import read_json, write_json
from .models import DedupeStats, Slide, SlideSet, Transcript, to_plain_dict
from .ocr import extract_text, text_similarity
from .utils import VideoToDocError, ms_to_seconds, run_command, seconds_to_ms


def detect_slides(video_path: Path, output_dir: Path, output_json: Path, settings: Settings, force: bool = False, skip_dedupe: bool = False) -> SlideSet:
    """检测课程讲义/PPT 截图。

    `fast` 只使用场景切换；`fine` 会加入固定间隔兜底点，避免渐变式
    翻页漏检；`audit` 额外保留候选截图和 HTML 审计页；`complete`
    会把候选点全部提升为最终截图，宁可多截也不漏页。

    当 skip_dedupe=True 时，只生成候选图不做去重。后续可由
    trim_candidates_by_transcript() 裁剪后再调用 deduplicate_slides()。
    """

    if output_json.exists() and not force:
        return slides_from_dict(read_json(output_json))

    output_dir.mkdir(parents=True, exist_ok=True)
    run_dir = output_dir.parent
    candidates_dir = run_dir / "slide_candidates"
    duration_ms = probe_duration_ms(video_path)
    change_points = detect_scene_changes(video_path, settings.scene_threshold)
    candidate_points = _candidate_points(change_points, duration_ms, settings)
    if settings.capture_mode in {"fine", "audit", "complete"}:
        write_candidate_audit(video_path, candidate_points, candidates_dir, run_dir / "slide_candidates.html", settings)
    boundaries = _build_boundaries(candidate_points, duration_ms, settings.min_slide_seconds)
    keep_all = settings.capture_mode == "complete" or settings.keep_all_candidates or skip_dedupe

    slides: list[Slide] = []
    previous_hashes: list[int] = []
    dedupe_stats = DedupeStats()
    for index, (start_ms, end_ms) in enumerate(boundaries, start=1):
        candidate_ms = _candidate_capture_ms(start_ms, end_ms, settings)
        candidate_path = _candidate_image_path(candidates_dir, candidate_points, candidate_ms)
        if not candidate_path.exists():
            extract_frame(video_path, candidate_ms, candidate_path, precise=False)
        image_hash = dhash(candidate_path)
        candidate_slide = Slide(
            slide_index=len(slides) + 1,
            image_path=str(candidate_path),
            start_ms=start_ms,
            end_ms=end_ms,
            capture_ms=candidate_ms,
            confidence=0.8,
            hash=f"{image_hash:016x}",
            edge_density=edge_density(candidate_path),
        )
        if not keep_all and slides and is_near_duplicate(
            candidate_slide,
            slides[-1],
            settings.hash_threshold,
            settings,
            dedupe_stats,
        ):
            if slides:
                old_start_ms = slides[-1].start_ms
                slides[-1].image_path = str(candidate_path)
                slides[-1].start_ms = old_start_ms
                slides[-1].end_ms = end_ms
                slides[-1].capture_ms = candidate_ms
                slides[-1].confidence = max(slides[-1].confidence, 0.8)
                slides[-1].hash = f"{image_hash:016x}"
                slides[-1].edge_density = candidate_slide.edge_density
                slides[-1].ocr_text = None
                previous_hashes[-1] = image_hash
            continue
        previous_hashes.append(image_hash)
        slides.append(candidate_slide)

    # skip_dedupe 模式下不做精确 seek 重提取和去重
    if not skip_dedupe:
        slides = refine_selected_slides(video_path, slides, output_dir, settings, candidates_dir)

    if not slides:
        fallback_path = output_dir / "0001.png"
        capture_ms = max(0, duration_ms - 1000)
        extract_frame(video_path, capture_ms, fallback_path)
        slides.append(Slide(1, str(fallback_path), 0, duration_ms, capture_ms, 0.3, f"{dhash(fallback_path):016x}"))

    slide_set = SlideSet(
        slides=slides,
        metadata={
            "scene_threshold": settings.scene_threshold,
            "hash_threshold": settings.hash_threshold,
            "duration_ms": duration_ms,
            "candidate_changes": change_points,
            "candidate_points": candidate_points,
            "capture_mode": settings.capture_mode,
            "keep_all_candidates": keep_all,
            "candidate_count": len(candidate_points),
            "dedupe_stats": to_plain_dict(dedupe_stats),
            "skip_dedupe": skip_dedupe,
        },
    )
    write_json(output_json, to_plain_dict(slide_set))
    return slide_set


def refine_selected_slides(video_path: Path, slides: list[Slide], output_dir: Path, settings: Settings, candidates_dir: Path | None = None) -> list[Slide]:
    refined: list[Slide] = []
    for index, slide in enumerate(slides, start=1):
        capture_ms, confidence = choose_capture_time(video_path, slide.start_ms, slide.end_ms, settings, candidates_dir)
        image_path = output_dir / f"{index:04d}.png"
        extract_frame(video_path, capture_ms, image_path, precise=True)
        refined.append(
            Slide(
                slide_index=index,
                image_path=str(image_path),
                start_ms=slide.start_ms,
                end_ms=slide.end_ms,
                capture_ms=capture_ms,
                confidence=confidence,
                hash=f"{dhash(image_path):016x}",
                edge_density=edge_density(image_path),
            )
        )
    return refined


def detect_scene_changes(video_path: Path, threshold: float) -> list[int]:
    expr = f"select=gt(scene\\,{threshold}),showinfo"
    result = run_command(
        ["ffmpeg", "-hide_banner", "-i", str(video_path), "-vf", expr, "-f", "null", "-"],
        timeout=600,
    )
    text = result.stderr + "\n" + result.stdout
    changes: list[int] = []
    for match in re.finditer(r"pts_time:([0-9.]+)", text):
        changes.append(seconds_to_ms(float(match.group(1))))
    return sorted(set(changes))


def write_candidate_audit(
    video_path: Path,
    candidate_points: list[int],
    candidates_dir: Path,
    html_path: Path,
    settings: Settings,
) -> None:
    candidates_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for index, point in enumerate(candidate_points, start=1):
        image_path = candidates_dir / f"candidate_{index:04d}_{point}.png"
        if not image_path.exists():
            extract_frame(video_path, point, image_path, precise=False)
        rows.append(
            "<tr>"
            f"<td>{index}</td><td>{point}</td><td>{ms_to_seconds(point):.2f}s</td>"
            f"<td><img src='{image_path.name}' loading='lazy'></td>"
            "</tr>"
        )
    html_path.write_text(
        "\n".join(
            [
                "<!doctype html><html><head><meta charset='utf-8'>",
                "<title>VideoToDoc 截图候选审计</title>",
                "<style>body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;margin:24px}"
                "table{border-collapse:collapse}td,th{border:1px solid #ddd;padding:6px}"
                "img{width:320px;height:auto}</style></head><body>",
                f"<h1>截图候选审计</h1><p>模式：{settings.capture_mode}，候选数：{len(candidate_points)}</p>",
                "<table><thead><tr><th>#</th><th>ms</th><th>time</th><th>frame</th></tr></thead><tbody>",
                *rows,
                "</tbody></table></body></html>",
            ]
        ),
        encoding="utf-8",
    )


def _candidate_image_path(candidates_dir: Path, candidate_points: list[int], point: int) -> Path:
    try:
        index = candidate_points.index(point) + 1
    except ValueError:
        index = 0
    if index:
        return candidates_dir / f"candidate_{index:04d}_{point}.png"
    return candidates_dir / f"candidate_{point}.png"


def _candidate_capture_ms(start_ms: int, end_ms: int, settings: Settings) -> int:
    margin_ms = max(0, int(settings.capture_margin_ms))
    return max(start_ms, end_ms - margin_ms)


def choose_capture_time(video_path: Path, start_ms: int, end_ms: int, settings: Settings, candidates_dir: Path | None = None) -> tuple[int, float]:
    if end_ms <= start_ms:
        return start_ms, 0.1
    window_ms = int(settings.stability_window_seconds * 1000)
    margin_ms = max(0, int(settings.capture_margin_ms))
    sample_start = max(start_ms, end_ms - window_ms)
    sample_end = max(sample_start + 1, end_ms - margin_ms)
    step_ms = max(100, int(1000 / max(1, settings.refine_fps)))
    times = list(range(sample_start, sample_end, step_ms))
    if not times or times[-1] < sample_end:
        times.append(sample_end)

    tmp_dir = tempfile.mkdtemp(prefix="videotodoc_frames_")
    hashes: list[tuple[int, int]] = []
    try:
        if candidates_dir and candidates_dir.exists():
            for capture_ms in times:
                matches = list(candidates_dir.glob(f"candidate_*_{capture_ms}.png"))
                if not matches:
                    matches = list(candidates_dir.glob(f"candidate_{capture_ms}.png"))
                if matches:
                    hashes.append((capture_ms, dhash(matches[0])))

        missing_times = [t for t in times if not any(h[0] == t for h in hashes)]
        for offset, capture_ms in enumerate(missing_times):
            frame_path = Path(tmp_dir) / f"frame_{start_ms}_{end_ms}_{offset}.png"
            extract_frame(video_path, capture_ms, frame_path)
            hashes.append((capture_ms, dhash(frame_path)))

        hashes.sort()
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    if len(hashes) < 2:
        return max(start_ms, end_ms - 300), 0.4

    stable_suffix: list[tuple[int, int]] = [hashes[-1]]
    for current, nxt in zip(reversed(hashes[:-1]), reversed(hashes[1:])):
        if hamming_distance(current[1], nxt[1]) <= settings.hash_threshold:
            stable_suffix.append(current)
        else:
            break
    stable_suffix.sort()
    confidence = min(0.95, 0.45 + len(stable_suffix) / max(1, len(hashes)) * 0.5)
    return stable_suffix[-1][0], confidence


def extract_frame(video_path: Path, capture_ms: int, output_path: Path, precise: bool = True) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if precise:
        # 最终入选截图必须使用精确 seek；把 -ss 放在 -i 后面虽然慢一点，
        # 但能避免快速 seek 跳到下一页关键帧，导致上一页末帧丢失。
        args = [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-ss",
            f"{ms_to_seconds(capture_ms):.3f}",
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(output_path),
        ]
    else:
        # 候选审计图只用于人工浏览和粗筛，优先速度。
        args = [
            "ffmpeg",
            "-y",
            "-ss",
            f"{ms_to_seconds(capture_ms):.3f}",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(output_path),
        ]
    run_command(args, timeout=30)


def dhash(image_path: Path, hash_size: int = 8) -> int:
    with Image.open(image_path) as image:
        grayscale = image.convert("L").resize((hash_size + 1, hash_size))
        pixels = list(grayscale.getdata())
    value = 0
    for row in range(hash_size):
        for col in range(hash_size):
            left = pixels[row * (hash_size + 1) + col]
            right = pixels[row * (hash_size + 1) + col + 1]
            value = (value << 1) | int(left > right)
    return value


def edge_density(image_path: Path) -> float:
    with Image.open(image_path) as image:
        edges = image.convert("L").filter(ImageFilter.FIND_EDGES)
        pixels = list(edges.getdata())
    if not pixels:
        return 0.0
    active = sum(1 for pixel in pixels if pixel > 32)
    return active / len(pixels)


def hamming_distance(left: int, right: int) -> int:
    return (left ^ right).bit_count()


def _get_slide_hash(slide: Slide) -> int:
    if slide.hash:
        return int(slide.hash, 16)
    h = dhash(Path(slide.image_path))
    slide.hash = f"{h:016x}"
    return h


def _get_slide_ocr_text(slide: Slide) -> str:
    if slide.ocr_text is not None:
        return slide.ocr_text
    text = extract_text(slide.image_path)
    slide.ocr_text = text
    return text


def is_near_duplicate(
    current: Slide,
    previous: Slide,
    hash_threshold: int,
    settings: Settings | None = None,
    stats: DedupeStats | None = None,
) -> bool:
    """判断相邻两张是否为同一页的轻微变化。

    单纯 dHash 对白底 PPT 太粗，会把不同标题页误合并；这里要求 hash 相近
    且缩略图真实变化面积很小，才认为是重复页。
    """

    current_path = Path(current.image_path)
    previous_path = Path(previous.image_path)

    change_ratio = image_change_ratio(current_path, previous_path)
    current_hash = _get_slide_hash(current)
    previous_hash = _get_slide_hash(previous)
    hash_distance = hamming_distance(current_hash, previous_hash)
    hash_close = hash_distance <= hash_threshold

    duplicate_change_threshold = settings.duplicate_change_threshold if settings else 0.005
    different_change_threshold = settings.different_change_threshold if settings else 0.12
    different_hash_threshold = settings.different_hash_threshold if settings else 16

    if hash_close and change_ratio < duplicate_change_threshold:
        if stats:
            stats.obvious_duplicates += 1
        return True

    if change_ratio >= different_change_threshold or hash_distance > different_hash_threshold:
        if stats:
            stats.obvious_different += 1
        return False

    if settings and settings.ocr_dedupe:
        if stats:
            stats.ocr_checks += 1
        current_text = _get_slide_ocr_text(current)
        previous_text = _get_slide_ocr_text(previous)
        similarity = text_similarity(current_text, previous_text)
        if similarity >= settings.ocr_similarity_threshold and change_ratio < different_change_threshold:
            if stats:
                stats.ocr_duplicates += 1
            return True
        if current_text and previous_text and similarity < settings.ocr_similarity_threshold:
            if stats:
                stats.ocr_kept += 1
            return False

    fallback_duplicate = hash_close and change_ratio < 0.02
    if stats:
        if fallback_duplicate:
            stats.obvious_duplicates += 1
        else:
            stats.obvious_different += 1
    return fallback_duplicate


def image_change_ratio(image_path: Path, previous_path: Path, threshold: int = 24) -> float:
    with Image.open(image_path) as current, Image.open(previous_path) as previous:
        left = current.convert("RGB").resize((320, 240))
        right = previous.convert("RGB").resize((320, 240))
        diff = ImageChops.difference(left, right).convert("L")
        pixels = list(diff.getdata())
    if not pixels:
        return 0.0
    return sum(1 for pixel in pixels if pixel > threshold) / len(pixels)


def slides_from_dict(data: dict) -> SlideSet:
    return SlideSet(slides=[Slide(**item) for item in data.get("slides", [])], metadata=data.get("metadata", {}))


def _candidate_points(change_points: list[int], duration_ms: int, settings: Settings) -> list[int]:
    """生成候选截图时间点。

    固定间隔决定候选点数量。场景变化点仅在所属间隔窗口内微调
    capture_ms 到最近的变化时刻，不产生额外候选点。
    """
    if settings.capture_mode not in {"fine", "audit", "complete"} or settings.fallback_interval_sec <= 0:
        return sorted(p for p in change_points if 0 < p < duration_ms)

    interval_ms = int(settings.fallback_interval_sec * 1000)
    # 纯间隔点
    interval_points = list(range(interval_ms, duration_ms, interval_ms))

    if not change_points:
        return interval_points

    # 对每个间隔点，找最近的场景变化点做微调
    result: list[int] = []
    for ip in interval_points:
        window_start = ip - interval_ms
        window_end = ip + interval_ms
        # 在 [window_start, window_end) 范围内找最近的场景变化点
        candidates_in_window = [cp for cp in change_points if window_start <= cp < window_end]
        if candidates_in_window:
            best = min(candidates_in_window, key=lambda cp: abs(cp - ip))
            result.append(best)
        else:
            result.append(ip)

    return sorted(set(p for p in result if 0 < p < duration_ms))


def _build_boundaries(change_points: list[int], duration_ms: int, min_slide_seconds: float) -> list[tuple[int, int]]:
    min_gap = int(min_slide_seconds * 1000)
    filtered: list[int] = []
    last = -math.inf
    for point in change_points:
        if point - last >= min_gap and 0 < point < duration_ms:
            filtered.append(point)
            last = point
    points = [0, *filtered, duration_ms]
    return [(points[index], points[index + 1]) for index in range(len(points) - 1) if points[index + 1] > points[index]]


def deduplicate_slides(
    candidates: SlideSet,
    settings: Settings,
) -> SlideSet:
    """对候选图做相邻页图像/OCR 去重。

    用于 ASR 段裁剪之后的跨段重复画面处理。比如同一张 PPT 被多个
    ASR 段引用，裁剪后仍需去重。

    同一图片路径（trim 阶段可能让多个 ASR 段指向同一张图）不会被判为
    重复合并——它们共享同一画面但对应不同的 ASR 段，合并后一张图可以
    对应多条段（这是正确的）。只有画面内容相同但来自不同截图文件的相邻
    slide 才会合并。

    Args:
        candidates: 已裁剪的候选图集合
        settings: 配置对象

    Returns:
        去重后的 SlideSet
    """
    if not candidates.slides:
        return candidates

    dedupe_stats = DedupeStats()
    kept: list[Slide] = []

    for slide in candidates.slides:
        # 同一图片路径 → 不走图像比较，直接合并为"一图多段"
        if kept and kept[-1].image_path == slide.image_path:
            kept[-1] = Slide(
                slide_index=kept[-1].slide_index,
                image_path=slide.image_path,
                start_ms=kept[-1].start_ms,
                end_ms=slide.end_ms,
                capture_ms=slide.capture_ms,
                confidence=max(kept[-1].confidence, slide.confidence),
                hash=slide.hash,
                edge_density=slide.edge_density,
                ocr_text=slide.ocr_text if slide.ocr_text is not None else kept[-1].ocr_text,
            )
            continue

        if kept and is_near_duplicate(
            slide,
            kept[-1],
            settings.hash_threshold,
            settings,
            dedupe_stats,
        ):
            kept[-1] = Slide(
                slide_index=kept[-1].slide_index,
                image_path=slide.image_path,
                start_ms=kept[-1].start_ms,
                end_ms=slide.end_ms,
                capture_ms=slide.capture_ms,
                confidence=max(kept[-1].confidence, slide.confidence, 0.8),
                hash=slide.hash,
                edge_density=slide.edge_density,
                ocr_text=None,
            )
            continue

        kept.append(
            Slide(
                slide_index=len(kept) + 1,
                image_path=slide.image_path,
                start_ms=slide.start_ms,
                end_ms=slide.end_ms,
                capture_ms=slide.capture_ms,
                confidence=slide.confidence,
                hash=slide.hash,
                edge_density=slide.edge_density,
                ocr_text=slide.ocr_text,
            )
        )

    # 重新编号
    for index, slide in enumerate(kept, start=1):
        slide.slide_index = index

    metadata = dict(candidates.metadata)
    metadata["dedupe_stats"] = to_plain_dict(dedupe_stats)
    metadata["deduplicated"] = True

    return SlideSet(slides=kept, metadata=metadata)


def trim_candidates_by_transcript(
    candidates: SlideSet,
    transcript: Transcript,
    video_path: Path,
    output_dir: Path,
    settings: Settings,
) -> SlideSet:
    """双向去重：按 ASR 段与候选图的时间轴对齐。

    方向 A（一段话多图 → 留最后一张）：
        同一 ASR 段内可能有多张候选图，只保留 capture_ms 最大的那张。

    方向 B（一张图多段话 → 归到 capture_ms 所在的那段）：
        每张图只有一个 capture_ms 时间点，它落在哪个 ASR 段的
        [start_ms, end_ms) 区间，就只归属那一段。后续 align_sections
        只把该段文字匹配给这张图，不会出现同一段文字出现在多页的情况。

    无图可匹配的 ASR 段：在中点自动提取一帧。
    """
    if not transcript.segments:
        return candidates

    output_dir.mkdir(parents=True, exist_ok=True)

    # 方向 A：每个 ASR 段内只保留 capture_ms 最大的候选图
    seg_to_best_slide: dict[int, Slide] = {}
    for seg_index, segment in enumerate(transcript.segments):
        seg_start_ms = segment.start_ms
        seg_end_ms = segment.end_ms
        matching = [
            slide for slide in candidates.slides
            if seg_start_ms <= slide.capture_ms < seg_end_ms
        ]
        if matching:
            seg_to_best_slide[seg_index] = max(matching, key=lambda s: s.capture_ms)

    # 方向 B：每张图只归属到 capture_ms 落在的那一段（自然满足，因为一张图只有一个 capture_ms）
    # 但多段可能选了同一张图，此时需要去重：该图只保留在 capture_ms 所在的段
    # 先按 capture_ms 归属做一次反向映射
    image_to_seg: dict[str, int] = {}
    for seg_index, slide in seg_to_best_slide.items():
        # 同一张图如果被多个段选中，只保留 capture_ms 准确落在的那一段
        # 由于上面的匹配逻辑是 seg_start <= capture < seg_end，
        # 一张图只可能落在一个段里，所以不需要额外去重
        image_to_seg[slide.image_path] = seg_index

    # 构建结果：为每个 ASR 段分配一张图
    trimmed_slides: list[Slide] = []
    for seg_index, segment in enumerate(transcript.segments):
        seg_start_ms = segment.start_ms
        seg_end_ms = segment.end_ms
        seg_mid_ms = (seg_start_ms + seg_end_ms) // 2

        if seg_index in seg_to_best_slide:
            slide = seg_to_best_slide[seg_index]
            trimmed_slides.append(
                Slide(
                    slide_index=len(trimmed_slides) + 1,
                    image_path=slide.image_path,
                    start_ms=slide.start_ms,
                    end_ms=slide.end_ms,
                    capture_ms=slide.capture_ms,
                    confidence=slide.confidence,
                    hash=slide.hash,
                    edge_density=slide.edge_density,
                    ocr_text=slide.ocr_text,
                )
            )
        # 无候选图的 ASR 段不补帧：auto 模式逐段补帧会导致每句一页的碎片化，
        # 改由 align_sections 将无图段文字归并到最近的候选图所在页。

    metadata = dict(candidates.metadata)
    metadata["trimmed_by_transcript"] = True
    metadata["segment_count"] = len(transcript.segments)
    metadata["trimmed_slide_count"] = len(trimmed_slides)

    return SlideSet(slides=trimmed_slides, metadata=metadata)


def finalize_segment_slides(
    segment: dict,
    candidates: SlideSet,
    video_path: Path,
    output_dir: Path,
    settings: Settings,
) -> list[Slide]:
    """对单个 segment 选 1 张最佳截图，返回 [Slide]。

    选择策略：
    1. 段内有候选图 → 选 edge_density 最高的（信息量最大）
    2. 段内无候选图 → 段中点快速补一帧
    slide 的时间范围设为段的 [start_ms, end_ms]，
    使 align_sections 将段内所有 transcript 文字归到这一页。
    """
    seg_start = segment["start_ms"]
    seg_end = segment["end_ms"]
    slide_ids = set(segment.get("candidate_slide_ids", []))

    # 取该 segment 的候选图
    seg_candidates = [s for s in candidates.slides if s.slide_index in slide_ids]

    if seg_candidates:
        # 选 edge_density 最高的候选图
        best = max(seg_candidates, key=lambda s: s.edge_density or 0.0)
        return [Slide(
            slide_index=1,
            image_path=best.image_path,
            start_ms=seg_start,
            end_ms=seg_end,
            capture_ms=best.capture_ms,
            confidence=best.confidence,
            hash=best.hash,
            edge_density=best.edge_density,
            ocr_text=best.ocr_text,
        )]

    # 段内无候选图 → 中点补一帧
    mid_ms = (seg_start + seg_end) // 2
    img_path = output_dir / f"fill_{segment['id']}_mid.png"
    extract_frame(video_path, mid_ms, img_path, precise=False)
    return [Slide(
        slide_index=1,
        image_path=str(img_path),
        start_ms=seg_start,
        end_ms=seg_end,
        capture_ms=mid_ms,
        confidence=0.6,
        hash=f"{dhash(img_path):016x}",
        edge_density=edge_density(img_path),
    )]


def cross_segment_dedupe(segments_slides: list[list[Slide]], settings: Settings) -> None:
    """跨段边界去重：相邻段末帧与首帧重复则删后者。"""
    for i in range(len(segments_slides) - 1):
        if not segments_slides[i] or not segments_slides[i + 1]:
            continue
        last = segments_slides[i][-1]
        first = segments_slides[i + 1][0]
        if is_near_duplicate(
            first, last,
            settings.hash_threshold, settings, DedupeStats(),
        ):
            segments_slides[i + 1].pop(0)
