"""关键词提取 + OCR overlap 测试（任务 4）。"""

import re


def test_extract_keywords_chinese() -> None:
    from videotodoc.slides import _extract_keywords
    kw = _extract_keywords("推导 LLM")
    assert "推导" in kw
    assert "导L" in kw
    assert "LL" in kw
    assert "LM" in kw
    assert len(kw) == 4


def test_extract_keywords_strips_punctuation() -> None:
    from videotodoc.slides import _extract_keywords
    kw = _extract_keywords("推导LLM，大语言模型！")
    # 应去除标点
    assert "推导" in kw
    assert "，" not in "".join(kw)


def test_extract_keywords_short_text_returns_empty() -> None:
    from videotodoc.slides import _extract_keywords
    assert _extract_keywords("a") == set()
    assert _extract_keywords("") == set()


def test_ocr_keyword_overlap_perfect_match() -> None:
    from videotodoc.slides import _ocr_keyword_overlap
    seg = "推导 LLM 大语言模型"
    ocr = "LLM 大语言模型 涌现"
    score = _ocr_keyword_overlap(seg, ocr)
    assert score > 0.0
    assert score <= 1.0


def test_ocr_keyword_overlap_no_match() -> None:
    from videotodoc.slides import _ocr_keyword_overlap
    assert _ocr_keyword_overlap("推导 LLM", "天津一日游") == 0.0


def test_ocr_keyword_overlap_empty_ocr() -> None:
    from videotodoc.slides import _ocr_keyword_overlap
    assert _ocr_keyword_overlap("推导 LLM", "") == 0.0
    assert _ocr_keyword_overlap("推导 LLM", None) == 0.0


def test_ocr_keyword_overlap_empty_seg() -> None:
    from videotodoc.slides import _ocr_keyword_overlap
    assert _ocr_keyword_overlap("", "LLM") == 0.0
