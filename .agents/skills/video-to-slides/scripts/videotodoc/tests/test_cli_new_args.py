"""CLI 新参数透传测试（任务 10）。"""


def test_cli_accepts_keep_all_candidates() -> None:
    """--keep-all-candidates 参数存在。"""
    from videotodoc.cli import build_parser
    parser = build_parser()
    args = parser.parse_args(["process", "/tmp/x.mp4", "--keep-all-candidates"])
    assert args.keep_all_candidates is True


def test_cli_accepts_max_candidates() -> None:
    from videotodoc.cli import build_parser
    parser = build_parser()
    args = parser.parse_args(["process", "/tmp/x.mp4", "--max-candidates", "300"])
    assert args.max_candidates == 300


def test_cli_accepts_match_window_sec() -> None:
    from videotodoc.cli import build_parser
    parser = build_parser()
    args = parser.parse_args(["process", "/tmp/x.mp4", "--match-window-sec", "8"])
    assert args.match_window_sec == 8.0
