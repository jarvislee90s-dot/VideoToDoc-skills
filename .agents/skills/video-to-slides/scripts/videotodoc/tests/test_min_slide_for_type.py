"""_min_slide_seconds_for_type 映射测试（任务 2）。"""

from videotodoc.slides import _min_slide_seconds_for_type


def test_talking_head_returns_5s() -> None:
    assert _min_slide_seconds_for_type("talking_head", 1.0) == 5.0


def test_lecture_slides_returns_0_5s() -> None:
    assert _min_slide_seconds_for_type("lecture_slides", 1.0) == 0.5


def test_screen_recording_returns_1s() -> None:
    assert _min_slide_seconds_for_type("screen_recording", 1.0) == 1.0


def test_movie_cinematic_returns_0_5s() -> None:
    assert _min_slide_seconds_for_type("movie_cinematic", 1.0) == 0.5


def test_unknown_returns_base() -> None:
    assert _min_slide_seconds_for_type("tutorial", 2.0) == 2.0
    assert _min_slide_seconds_for_type("auto", 1.0) == 1.0
