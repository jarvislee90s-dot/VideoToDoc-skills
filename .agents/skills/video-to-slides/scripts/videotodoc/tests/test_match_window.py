"""_match_window 匹配窗口边界测试（任务 3）。"""


def test_match_window_long_segment() -> None:
    from videotodoc.slides import _match_window
    # 段长 30s, W=5s
    assert _match_window(0, 30000, 5000) == (25000, 30000)


def test_match_window_short_segment_backoff() -> None:
    from videotodoc.slides import _match_window
    # 段长 4s, W=5s → 回退到段长
    assert _match_window(0, 4000, 5000) == (0, 4000)


def test_match_window_exact_length() -> None:
    from videotodoc.slides import _match_window
    # 段长 5s, W=5s
    assert _match_window(1000, 6000, 5000) == (1000, 6000)


def test_match_window_within_long_segment() -> None:
    from videotodoc.slides import _match_window
    # 段长 100s, W=8s → 末 8s
    assert _match_window(5000, 105000, 8000) == (97000, 105000)
