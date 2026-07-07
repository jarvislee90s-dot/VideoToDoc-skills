from __future__ import annotations

import math
import re
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Literal

from PIL import Image, ImageFilter
from PIL import ImageChops

from .audio import probe_duration_ms
from .config import Settings
from .io import read_json, write_json
from .models import DedupeStats, Slide, SlideSet, Transcript, to_plain_dict
from .ocr import extract_text, text_similarity
from .utils import VideoToDocError, ms_to_seconds, run_command, seconds_to_ms


VideoType = Literal[
    "lecture_slides", "talking_head", "screen_recording", "movie_cinematic", "tutorial"
]


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
    # 按视频类型调整场景检测阈值（auto 时用 settings.scene_threshold）
    scene_threshold = _scene_threshold_for_type(settings.video_type, settings.scene_threshold)
    change_points = detect_scene_changes(video_path, scene_threshold)
    candidate_points = _candidate_points(change_points, duration_ms, settings)
    if settings.capture_mode in {"fine", "audit", "complete"}:
        write_candidate_audit(video_path, candidate_points, candidates_dir, run_dir / "slide_candidates.html", settings)
    boundaries = _build_boundaries(candidate_points, duration_ms, settings.min_slide_seconds)
    keep_all = settings.capture_mode == "complete" or settings.keep_all_candidates or skip_dedupe

    slides: list[Slide] = []
    previous_hashes: list[int] = []
    dedupe_stats = DedupeStats()

    def _extract_candidate(args: tuple[int, int, int]) -> tuple[int, int, int, Path, int, float]:
        idx, start_ms, end_ms = args
        candidate_ms = _candidate_capture_ms(start_ms, end_ms, settings)
        candidate_path = _candidate_image_path(candidates_dir, candidate_points, candidate_ms)
        if not candidate_path.exists():
            extract_frame(video_path, candidate_ms, candidate_path, precise=False)
        image_hash = dhash(candidate_path)
        ed = edge_density(candidate_path)
        return (idx, start_ms, end_ms, candidate_path, image_hash, ed)

    task_args = [(i, s, e) for i, (s, e) in enumerate(boundaries)]
    precomputed: dict[int, tuple[int, int, Path, int, float]] = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(_extract_candidate, arg): arg[0] for arg in task_args}
        for future in as_completed(futures):
            idx, start_ms, end_ms, candidate_path, image_hash, ed = future.result()
            precomputed[idx] = (start_ms, end_ms, candidate_path, image_hash, ed)

    for idx in range(len(boundaries)):
        start_ms, end_ms, candidate_path, image_hash, ed = precomputed[idx]
        candidate_ms = _candidate_capture_ms(start_ms, end_ms, settings)
        candidate_slide = Slide(
            slide_index=len(slides) + 1,
            image_path=str(candidate_path),
            start_ms=start_ms,
            end_ms=end_ms,
            capture_ms=candidate_ms,
            confidence=0.8,
            hash=f"{image_hash:016x}",
            edge_density=ed,
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
                slides[-1].edge_density = ed
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
    def _refine_one(args: tuple[int, Slide]) -> tuple[int, Slide]:
        index, slide = args
        capture_ms, confidence = choose_capture_time(video_path, slide.start_ms, slide.end_ms, settings, candidates_dir)
        image_path = output_dir / f"{index:04d}.png"
        extract_frame(video_path, capture_ms, image_path, precise=True)
        refined_slide = Slide(
            slide_index=index,
            image_path=str(image_path),
            start_ms=slide.start_ms,
            end_ms=slide.end_ms,
            capture_ms=capture_ms,
            confidence=confidence,
            hash=f"{dhash(image_path):016x}",
            edge_density=edge_density(image_path),
        )
        return (index, refined_slide)

    task_args = list(enumerate(slides, start=1))
    results: dict[int, Slide] = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(_refine_one, arg): arg[0] for arg in task_args}
        for future in as_completed(futures):
            idx, slide = future.result()
            results[idx] = slide

    refined = [results[i] for i in range(1, len(slides) + 1)]
    return refined


def _classify_by_features(scene_rate: float, edge_density: float, saturation_mean: float) -> VideoType:
    """按场景变化率/边缘密度/饱和度判型（纯函数，便于测试）。

    阈值参考 videoQuickNote classify_video，适配本项目的 detect_scene_changes 口径。
    """
    if scene_rate < 0.05 and edge_density > 0.15:
        return "lecture_slides"
    if scene_rate < 0.03 and saturation_mean < 60 and edge_density < 0.10:
        return "talking_head"
    if scene_rate < 0.10 and edge_density > 0.20 and saturation_mean < 80:
        return "screen_recording"
    if scene_rate > 0.30:
        return "movie_cinematic"
    return "tutorial"


def _scene_threshold_for_type(video_type: str, base: float) -> float:
    """按视频类型调整场景变化检测阈值（越大越宽松，越少检出）。"""
    if video_type == "talking_head":
        return 0.20      # 宽松：出镜讲解画面变化多为无意义，少产生候选
    if video_type == "lecture_slides":
        return 0.03      # 敏感：PPT 翻页要检出
    if video_type == "screen_recording":
        return 0.08
    return base          # auto/movie_cinematic/tutorial 用配置值


def _min_slide_seconds_for_type(video_type: str, base: float) -> float:
    """按 video_type 返回 min_slide_seconds 基线值（秒）。

    talking_head 5s（人脸动作不能算换页点）
    lecture_slides/movie_cinematic 0.5s（PPT 翻页/镜头切换快）
    screen_recording 1s
    其他用 base
    """
    if video_type == "talking_head":
        return 5.0
    if video_type in ("lecture_slides", "movie_cinematic"):
        return 0.5
    if video_type == "screen_recording":
        return 1.0
    return base


def _max_candidates_for_type(video_type: str, base: int, duration_sec: float) -> int:
    """按 video_type + duration 算候选数硬上限。

    type_cap 表 + duration_factor 调整：duration_factor = max(1, duration/900)，
    每 15 分钟候选数翻倍，达 type_cap 即封顶。
    """
    type_caps = {
        "talking_head": 150,
        "lecture_slides": 500,
        "screen_recording": 400,
        "movie_cinematic": 800,
        "tutorial": 300,
    }
    type_cap = type_caps.get(video_type, base)
    duration_factor = max(1.0, duration_sec / 900.0)
    return min(type_cap, int(base * duration_factor))


def _mean_saturation(frame_bgr) -> float:
    """BGR 帧 → HSV 的 S 通道均值。"""
    import cv2
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    return float(hsv[:, :, 1].mean())


def _edge_density_from_array(frame_bgr) -> float:
    """从 BGR numpy 数组算边缘密度（与 edge_density(path) 口径一致，复用 PIL）。"""
    rgb = frame_bgr[:, :, ::-1].copy()
    image = Image.fromarray(rgb)
    edges = image.convert("L").filter(ImageFilter.FIND_EDGES)
    pixels = list(edges.getdata())
    if not pixels:
        return 0.0
    active = sum(1 for pixel in pixels if pixel > 32)
    return active / len(pixels)


def _sample_frames_for_classify(video_path: Path, n: int = 30) -> list:
    """均匀采样 n 帧（BGR ndarray），用于分类特征计算。"""
    import cv2
    import numpy as np
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return []
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames <= 0:
        cap.release()
        return []
    indices = np.linspace(0, total_frames - 1, n, dtype=int)
    frames = []
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ret, frame = cap.read()
        if ret and frame is not None:
            frames.append(frame)
    cap.release()
    return frames


def _compute_scene_rate(video_path: Path, threshold: float = 0.06) -> float:
    """场景变化点数 / 时长（次/秒）。复用 detect_scene_changes + probe_duration_ms。"""
    change_points = detect_scene_changes(video_path, threshold)
    duration_ms = probe_duration_ms(video_path)
    if duration_ms <= 0:
        return 0.0
    return len(change_points) / (duration_ms / 1000.0)


def classify_video(video_path: Path) -> VideoType:
    """采样帧 + 场景变化率 → 判定视频类型。无帧时回退 tutorial。"""
    import numpy as np
    frames = _sample_frames_for_classify(video_path, n=30)
    if not frames:
        return "tutorial"
    edge_densities = [_edge_density_from_array(f) for f in frames]
    saturations = [_mean_saturation(f) for f in frames]
    scene_rate = _compute_scene_rate(video_path)
    avg_edge = float(np.mean(edge_densities)) if edge_densities else 0.0
    avg_sat = float(np.mean(saturations)) if saturations else 0.0
    result = _classify_by_features(scene_rate, avg_edge, avg_sat)
    print(f"  🎬 视频类型判定：scene_rate={scene_rate:.4f} edge={avg_edge:.4f} sat={avg_sat:.1f} → {result}")
    return result


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
    """在 ASR 段末附近选一张信息量足够的截图。

    策略：
    1. 默认截图点为 end_ms - capture_margin_ms（保持原行为）。
    2. 计算默认帧的 edge_density；如果 >= min_edge_density，直接返回。
    3. 否则在 [default_ms - frame_drift_back_seconds, default_ms] 范围内
       按 250ms 步长向前（时间更早）搜索，选 edge_density 最高的帧。
    4. 搜索范围不跨出当前 segment [start_ms, end_ms]。
    5. 都没找到高密度帧时回退到默认点。

    注：这是轻量优化，只检查最终入选的 slide，不是全段扫描。
    """
    if end_ms <= start_ms:
        return start_ms, 0.1

    margin_ms = max(0, int(settings.capture_margin_ms))
    drift_ms = max(0, int(settings.frame_drift_back_seconds * 1000))
    step_ms = 250  # 250ms 步长，兼顾精度与速度

    default_ms = max(start_ms, end_ms - margin_ms)
    search_start = max(start_ms, default_ms - drift_ms)

    tmp_dir = tempfile.mkdtemp(prefix="videotodoc_frames_")
    try:
        def _get_frame(ms: int) -> tuple[Path, float]:
            """获取指定时间帧，优先复用候选图，否则临时精确提取。"""
            existing = None
            if candidates_dir and candidates_dir.exists():
                matches = list(candidates_dir.glob(f"candidate_*_{ms}.png"))
                if not matches:
                    matches = list(candidates_dir.glob(f"candidate_{ms}.png"))
                if matches:
                    existing = matches[0]

            if existing:
                frame_path = existing
            else:
                frame_path = Path(tmp_dir) / f"frame_{ms}.png"
                extract_frame(video_path, ms, frame_path, precise=True)

            return frame_path, edge_density(frame_path)

        # 默认帧优先
        _, default_density = _get_frame(default_ms)
        if default_density >= settings.min_edge_density:
            return default_ms, min(0.95, 0.5 + default_density * 10)

        # 默认帧信息密度低，向前漂移搜索
        best_ms = default_ms
        best_density = default_density
        for ms in range(default_ms - step_ms, search_start - 1, -step_ms):
            _, density = _get_frame(ms)
            if density > best_density:
                best_ms = ms
                best_density = density
                # 找到满足阈值的即可提前结束
                if density >= settings.min_edge_density:
                    break

        confidence = min(0.95, 0.5 + best_density * 10)
        return best_ms, confidence
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


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

    # 构建结果：每个 ASR 段一张图，时间范围用段边界，capture 取段末 - margin
    margin_ms = max(0, int(settings.capture_margin_ms))
    trimmed_slides: list[Slide] = []
    for seg_index, segment in enumerate(transcript.segments):
        seg_start_ms = segment.start_ms
        seg_end_ms = segment.end_ms
        # 段末取帧点（不早于段首）
        end_capture_ms = max(seg_start_ms, seg_end_ms - margin_ms)

        if seg_index in seg_to_best_slide:
            src = seg_to_best_slide[seg_index]
            trimmed_slides.append(
                Slide(
                    slide_index=len(trimmed_slides) + 1,
                    image_path=src.image_path,
                    start_ms=seg_start_ms,       # 段边界（不再是候选图窗口）
                    end_ms=seg_end_ms,           # 段边界
                    capture_ms=end_capture_ms,   # 段末 - margin
                    confidence=src.confidence,
                    hash=src.hash,
                    edge_density=src.edge_density,
                    ocr_text=src.ocr_text,
                )
            )
        elif settings.video_type == "talking_head":
            # talking_head 无候选图段 → 段末直接取帧，不再跳过
            img_path = output_dir / f"trim_end_{seg_index:03d}_{end_capture_ms}.png"
            extract_frame(video_path, end_capture_ms, img_path, precise=True)
            # dhash/edge_density 可能因帧提取失败而抛异常，做防御
            try:
                slide_hash = f"{dhash(img_path):016x}" if img_path.exists() else "0" * 16
            except Exception:
                slide_hash = "0" * 16
            try:
                slide_edge = edge_density(img_path) if img_path.exists() else 0.0
            except Exception:
                slide_edge = 0.0
            trimmed_slides.append(
                Slide(
                    slide_index=len(trimmed_slides) + 1,
                    image_path=str(img_path),
                    start_ms=seg_start_ms,
                    end_ms=seg_end_ms,
                    capture_ms=end_capture_ms,
                    confidence=0.3,
                    hash=slide_hash,
                    edge_density=slide_edge,
                )
            )
        # 非 talking_head 且无候选图：保持原行为（不补帧，由 align 归并）

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
