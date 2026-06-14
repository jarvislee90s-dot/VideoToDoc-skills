from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_PROMPT = """这是一个课程/讲座录音，主要为中文讲解，可能包含数学公式、金融术语、英文专业术语和软件名。
请准确保留英文术语原拼写，不要翻译，例如 API、Python、GitHub。
数学符号和表达式尽量使用标准格式，例如 +、-、×、÷、=、≠、≈、≤、≥、∑、∫、∂、Δ、α、β、γ。
请补全合理标点，避免无根据扩写；听不清处标记为 [听不清]。"""


@dataclass
class Settings:
    """VideoToDoc 的运行配置。

    默认值偏向 Apple Silicon 本地运行：`mlx-whisper` 负责真实转录，
    Agent 负责摘要/思维导图等智能整理，不强制依赖外部 LLM key。
    """

    asr_backend: str = "mlx-whisper"
    asr_model: str = "mlx-community/whisper-large-v3-turbo"
    language: str = "zh"
    audio_profile: str = "auto"
    capture_mode: str = "fine"
    scene_threshold: float = 0.06
    hash_threshold: int = 8
    stability_window_seconds: float = 1.0
    refine_fps: int = 8
    min_slide_seconds: float = 1.5
    capture_margin_ms: int = 500
    fallback_interval_sec: int = 15
    keep_all_candidates: bool = False
    ocr_dedupe: bool = False
    ocr_similarity_threshold: float = 0.92
    duplicate_change_threshold: float = 0.005
    different_change_threshold: float = 0.12
    different_hash_threshold: int = 16
    sync_offset_ms: int | None = None
    low_confidence_threshold: float = 0.55
    mindmap_backend: str = "agent"
    mindmap_model: str = "gpt-4o-mini"
    feishu_folder_token: str = ""
    feishu_identity: str = "user"
    prompt: str = DEFAULT_PROMPT
    terms: dict[str, str] = field(default_factory=dict)
    max_periods_per_segment: int = 3
    min_segment_chars: int = 30


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_config(path: Path | None) -> Settings:
    settings = Settings()
    if path and path.exists():
        data = _load_yaml_like(path)
        for key, value in data.items():
            if hasattr(settings, key):
                setattr(settings, key, value)
    load_dotenv(Path(".env"))
    return settings


def _load_yaml_like(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore

        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return loaded if isinstance(loaded, dict) else {}
    except ModuleNotFoundError:
        return _load_simple_yaml(path)


def _load_simple_yaml(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {}
    current_map: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if raw_line.startswith(" ") and current_map:
            key, _, value = raw_line.strip().partition(":")
            result.setdefault(current_map, {})[key] = _coerce_scalar(value.strip())
            continue
        key, _, value = raw_line.partition(":")
        key = key.strip()
        value = value.strip()
        if value == "":
            result[key] = {}
            current_map = key
        else:
            result[key] = _coerce_scalar(value)
            current_map = None
    return result


def _coerce_scalar(value: str) -> Any:
    if value in {"null", "None", "~"}:
        return None
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value
