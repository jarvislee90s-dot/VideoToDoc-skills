from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TranscriptSegment:
    start_ms: int
    end_ms: int
    text: str
    confidence: float | None = None
    words: list[WordTimestamp] = field(default_factory=list)


@dataclass
class WordTimestamp:
    start_ms: int
    end_ms: int
    word: str


@dataclass
class Transcript:
    backend: str
    language: str
    segments: list[TranscriptSegment]
    prompt: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Slide:
    slide_index: int
    image_path: str
    start_ms: int
    end_ms: int
    capture_ms: int
    confidence: float
    hash: str | None = None
    edge_density: float | None = None


@dataclass
class SlideSet:
    slides: list[Slide]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DedupeStats:
    obvious_duplicates: int = 0
    obvious_different: int = 0
    ocr_checks: int = 0
    ocr_duplicates: int = 0
    ocr_kept: int = 0


@dataclass
class Section:
    slide_index: int
    image_path: str
    start_ms: int
    end_ms: int
    capture_ms: int
    transcript: str
    segment_indexes: list[int]
    notes: list[str] = field(default_factory=list)


@dataclass
class ProcessResult:
    run_dir: Path
    transcript_path: Path
    slides_path: Path
    sections_path: Path
    markdown_path: Path
    mindmap_path: Path
    compact_markdown_path: Path | None = None
    semantic_markdown_path: Path | None = None
    mindmap_image_path: Path | None = None
    docx_path: Path | None = None
    semantic_docx_path: Path | None = None
    quality_report_path: Path | None = None


def to_plain_dict(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return {key: to_plain_dict(item) for key, item in asdict(value).items()}
    if isinstance(value, list):
        return [to_plain_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: to_plain_dict(item) for key, item in value.items()}
    return value
