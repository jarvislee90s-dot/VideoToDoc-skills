from __future__ import annotations

import re
import shutil
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Any

from .utils import run_command


def ocr_available() -> bool:
    return _rapidocr_available() or shutil.which("tesseract") is not None


@lru_cache(maxsize=512)
def extract_text(image_path: str) -> str:
    """用本地 OCR 提取图片文字。

    优先使用 RapidOCR，它对中文 PPT 更友好；如果 RapidOCR 未安装或模型
    未就绪，再降级到 tesseract CLI。没有 OCR 时返回空字符串。
    """

    text = _extract_text_rapidocr(image_path)
    if text:
        return normalize_ocr_text(text)
    try:
        result = run_command(["tesseract", image_path, "stdout", "-l", "chi_sim+eng", "--psm", "6"])
    except Exception:
        return ""
    return normalize_ocr_text(result.stdout)


def normalize_ocr_text(text: str) -> str:
    return re.sub(r"\s+", "", text).strip().lower()


def text_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def _rapidocr_available() -> bool:
    try:
        import rapidocr  # noqa: F401

        return True
    except ModuleNotFoundError:
        return False


@lru_cache(maxsize=1)
def _rapidocr_engine() -> Any | None:
    try:
        from rapidocr import RapidOCR  # type: ignore

        return RapidOCR()
    except Exception:
        return None


def _extract_text_rapidocr(image_path: str) -> str:
    engine = _rapidocr_engine()
    if engine is None:
        return ""
    try:
        result = engine(image_path)
    except Exception:
        return ""
    return _rapidocr_result_to_text(result)


def _rapidocr_result_to_text(result: Any) -> str:
    if result is None:
        return ""
    if hasattr(result, "txts"):
        return "\n".join(str(item) for item in getattr(result, "txts") or [])
    if isinstance(result, tuple) and result:
        return _rapidocr_result_to_text(result[0])
    if isinstance(result, list):
        texts: list[str] = []
        for item in result:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                if isinstance(item[1], (list, tuple)) and item[1]:
                    texts.append(str(item[1][0]))
                else:
                    texts.append(str(item[1]))
        return "\n".join(texts)
    return ""
