"""_max_candidates_for_type 动态调整算法测试（任务 2）。"""

from videotodoc.slides import _max_candidates_for_type


def test_short_video_returns_base_max() -> None:
    # 14min lecture_slides: 短视频不调整，返回 base
    result = _max_candidates_for_type("lecture_slides", 200, 840)
    assert result <= 500
    assert result >= 200


def test_long_video_caps_at_type_max() -> None:
    # 60min lecture_slides: 强制 ≤ 500（达到 type_cap）
    result = _max_candidates_for_type("lecture_slides", 200, 3600)
    assert result == 500


def test_movie_cinematic_long_video() -> None:
    # 60min movie_cinematic: type_cap=800
    result = _max_candidates_for_type("movie_cinematic", 200, 3600)
    assert result == 800


def test_talking_head_long_video() -> None:
    # 60min talking_head: type_cap=150
    result = _max_candidates_for_type("talking_head", 200, 3600)
    assert result == 150


def test_unknown_type_uses_base() -> None:
    # tutorial: type_cap=300
    result = _max_candidates_for_type("tutorial", 200, 3600)
    assert result == 300
