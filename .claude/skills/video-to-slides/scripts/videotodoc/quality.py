from __future__ import annotations

from pathlib import Path

from .io import write_text
from .models import Section, SlideSet, Transcript


def write_quality_report(
    output_path: Path,
    transcript: Transcript,
    slides: SlideSet,
    sections: list[Section],
    sync_offset_ms: int,
) -> Path:
    """生成给 Agent 看的质量检查报告。

    这个报告不是面向最终读者，而是为了防止 Agent 把 mock 转录、截图过少、
    文档缺图片等中间状态误判为可交付结果。
    """

    warnings: list[str] = []
    if transcript.backend == "mock":
        warnings.append("当前使用 mock ASR，讲稿不是视频真实转录。")
    if len(slides.slides) <= 3:
        warnings.append("最终截图数量不超过 3 页，请检查是否需要 audit/fine 模式或降低 scene_threshold。")
    if slides.metadata.get("capture_mode") == "complete":
        warnings.append("当前为 complete 模式：截图完整优先，可能包含重复页，适合后续人工/Agent 精简。")
    candidate_count = int(slides.metadata.get("candidate_count", 0) or 0)
    if candidate_count and candidate_count <= len(slides.slides):
        warnings.append("候选截图数量未明显多于最终截图，可能存在漏检风险。")
    empty_sections = [section.slide_index for section in sections if "empty_transcript_match" in section.notes]
    if empty_sections:
        warnings.append(f"存在无讲解匹配页面：{empty_sections}")

    lines = [
        "# VideoToDoc 质量报告",
        "",
        f"- ASR 后端：{transcript.backend}",
        f"- ASR 模型：{transcript.metadata.get('model', 'n/a')}",
        f"- 转录分段数：{len(transcript.segments)}",
        f"- 截图模式：{slides.metadata.get('capture_mode', 'n/a')}",
        f"- 场景候选数：{len(slides.metadata.get('candidate_changes', []))}",
        f"- 总候选点数：{candidate_count}",
        f"- 最终截图数：{len(slides.slides)}",
        f"- 图文段落数：{len(sections)}",
        f"- sync_offset_ms：{sync_offset_ms}",
        f"- 去重统计：{slides.metadata.get('dedupe_stats', {})}",
        "",
        "## 警告",
        "",
    ]
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("- 暂无明显质量警告。")
    lines.extend(["", "## 验收提示", "", "- 真实交付前请确认 ASR 后端不是 mock。", "- 打开 `slide_candidates.html` 检查是否漏掉 PPT 页面。", "- 抽查 `draft.docx` 中图片和讲稿是否对应。"])
    write_text(output_path, "\n".join(lines))
    return output_path
