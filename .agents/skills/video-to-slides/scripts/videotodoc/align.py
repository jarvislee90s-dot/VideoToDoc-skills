from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

from .models import Section, SlideSet, Transcript


# 句末标点：在区间边界回溯断句，避免切开句子成分（与 review 句法硬标准精神一致）
_SENTENCE_END = set("。！？；!?;")


def _pick_main_slide(slides: list) -> object:
    """从一组同段 slide 中选主图：优先 image_path 含 _main_ 标记，否则取 edge_density 最高者。"""
    for s in slides:
        if "_main_" in Path(s.image_path).stem:
            return s
    return max(slides, key=lambda s: s.edge_density or 0.0)


def _char_pos_for_ms(seg_text: str, seg_start_ms: int, seg_end_ms: int, target_ms: int) -> int:
    """按时间线性插值估算 target_ms 在 seg_text 中对应的字符位置。

    合并段无字级时间戳，用段级时间线性插值估算，不精确但足够定位断句点。
    保留供旧版/回滚路径使用，多图合并后不再调用。
    """
    if seg_end_ms <= seg_start_ms:
        return 0
    ratio = (target_ms - seg_start_ms) / (seg_end_ms - seg_start_ms)
    ratio = max(0.0, min(1.0, ratio))
    return int(ratio * len(seg_text))


def _snap_to_sentence_end(seg_text: str, pos: int) -> int:
    """从 pos 向前回溯到最近的句末标点之后，找不到返回 pos。

    保证切分点落在句子成分之间，不切断主谓宾。保留供旧版路径使用。
    """
    upper = min(pos, len(seg_text))
    for i in range(upper - 1, -1, -1):
        if seg_text[i] in _SENTENCE_END:
            return i + 1
    return pos


def align_sections(slides: SlideSet, transcript: Transcript, sync_offset_ms: int = 0) -> list[Section]:
    """将截图与 ASR 转录按时间轴对齐。

    按段合并分页（推荐行为）：
    - 段内只有一张图 → 整段归该图（保留原语义）。
    - 段内有多张图（keep_all_candidates 开启时）→ 整段文字归主图所在页，
      其余图作为附件图附在同一页，按 capture_ms 时间顺序排列，**不切分文字、不分页**。
    - 无图认领的 segment → 归最近图（保留原逻辑：后面的优先，否则前面）。
    - Section.image_paths 收集段内所有图路径（按 capture_ms 升序），
      供 Markdown/Word 渲染时把多张图放在同一页。
    """
    if not slides.slides or not transcript.segments:
        return []

    slides_list = slides.slides

    # capture → slide 映射（同 ms 取后定义者）
    capture_to_slide: dict[int, object] = {}
    for s in slides_list:
        capture_to_slide[s.capture_ms + sync_offset_ms] = s
    captures_sorted = sorted(capture_to_slide.keys())

    # 多图段分组：trim_candidates_by_transcript 会把同一段的多张图都设为
    # [seg_start_ms, seg_end_ms]，故相同 (start_ms, end_ms) 即同段多图。
    groups: list[list] = []
    range_to_group: dict[tuple[int, int], int] = {}
    for s in slides_list:
        key = (s.start_ms, s.end_ms)
        if key not in range_to_group:
            range_to_group[key] = len(groups)
            groups.append([s])
        else:
            groups[range_to_group[key]].append(s)

    main_slides: list = [_pick_main_slide(g) for g in groups]

    # 同组所有 slide_index → 主图 slide_index 的映射
    sid_to_main: dict[int, int] = {}
    for g, main in zip(groups, main_slides):
        for s in g:
            sid_to_main[s.slide_index] = main.slide_index

    # page_text/page_segs 仅按主图 sid 分桶
    main_sids = [s.slide_index for s in main_slides]
    page_text: dict[int, list[str]] = {sid: [] for sid in main_sids}
    page_segs: dict[int, list[int]] = {sid: [] for sid in main_sids}

    for seg_idx, seg in enumerate(transcript.segments):
        seg_s = seg.start_ms
        seg_e = seg.end_ms
        # 该 segment 包含的 capture_ms（落在 [seg_s, seg_e) 内）
        inner = [c for c in captures_sorted if seg_s <= c < seg_e]

        if not inner:
            # 无图认领 → 归最近图（后面的优先，否则前面）
            target = None
            for c in captures_sorted:
                if c >= seg_e:
                    target = sid_to_main[capture_to_slide[c].slide_index]
                    break
            if target is None:
                for c in reversed(captures_sorted):
                    if c <= seg_s:
                        target = sid_to_main[capture_to_slide[c].slide_index]
                        break
            if target is None:
                target = main_sids[0] if main_sids else slides_list[0].slide_index
            page_text[target].append(seg.text)
            page_segs[target].append(seg_idx)
        else:
            # 单图或多图：整段文字归主图，不切分、不分页
            first_sid = capture_to_slide[inner[0]].slide_index
            main_sid = sid_to_main[first_sid]
            page_text[main_sid].append(seg.text)
            page_segs[main_sid].append(seg_idx)

    # 生成 Section：每段一个，附件图通过 image_paths 承载
    sections: list[Section] = []
    # 连续重新编号 1..N（清除 trim 阶段多图跳号，保证页号连续）
    for page_no, (g, main_slide) in enumerate(zip(groups, main_slides), start=1):
        sid = main_slide.slide_index
        texts = [t for t in page_text[sid] if t]
        matched = "\n\n".join(texts) if texts else "本页无讲解。"
        notes: list[str] = [] if page_segs[sid] else ["empty_transcript_match"]
        # image_paths：段内所有图按 capture_ms 时间顺序排列
        sorted_imgs = sorted(g, key=lambda s: s.capture_ms)
        image_paths = [s.image_path for s in sorted_imgs]
        sections.append(
            Section(
                slide_index=page_no,
                image_path=main_slide.image_path,
                start_ms=main_slide.start_ms,
                end_ms=main_slide.end_ms,
                capture_ms=main_slide.capture_ms,
                transcript=matched,
                segment_indexes=page_segs[sid],
                notes=notes,
                image_paths=image_paths,
            )
        )
    return sections
