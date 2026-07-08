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


from dataclasses import dataclass


@dataclass
class _FakeSlide:
    edge_density: float = 0.0
    ocr_text: str = ""


def test_score_candidate_weighted_sum() -> None:
    from videotodoc.slides import _score_candidate
    s = _FakeSlide(edge_density=0.8, ocr_text="推导 LLM 大语言模型")
    # edge_normalized=0.8/0.8=1.0, ocr=seg_kw 完全包含 ocr_kw → overlap=1.0
    # score = 0.5*1.0 + 0.5*1.0 = 1.0
    score = _score_candidate(s, "推导 LLM 大语言模型", max_edge_in_seg=0.8,
                              edge_weight=0.5, ocr_weight=0.5)
    assert abs(score - 1.0) < 0.01


def test_score_candidate_normalizes_edge() -> None:
    from videotodoc.slides import _score_candidate
    s = _FakeSlide(edge_density=0.4, ocr_text="")
    # edge_normalized=0.4/0.8=0.5, ocr=0.0 (no ocr)
    # score = 0.5*0.5 + 0.5*0.0 = 0.25
    score = _score_candidate(s, "推导 LLM", max_edge_in_seg=0.8,
                              edge_weight=0.5, ocr_weight=0.5)
    assert abs(score - 0.25) < 0.01


def test_pick_main_candidate_highest_score() -> None:
    from videotodoc.slides import _pick_main_candidate
    slides = [
        _FakeSlide(edge_density=0.3, ocr_text=""),
        _FakeSlide(edge_density=0.8, ocr_text="推导 LLM"),
        _FakeSlide(edge_density=0.5, ocr_text=""),
    ]
    main = _pick_main_candidate(slides, "推导 LLM 大语言模型",
                                  edge_weight=0.5, ocr_weight=0.5)
    # 第二张 ocr 完全匹配 + edge 最高 → main
    assert main is slides[1]


def test_pick_main_candidate_single() -> None:
    from videotodoc.slides import _pick_main_candidate
    slides = [_FakeSlide(edge_density=0.5, ocr_text="x")]
    main = _pick_main_candidate(slides, "x", 0.5, 0.5)
    assert main is slides[0]


def test_pick_main_candidate_empty_raises() -> None:
    from videotodoc.slides import _pick_main_candidate
    import pytest
    with pytest.raises(ValueError):
        _pick_main_candidate([], "x", 0.5, 0.5)
