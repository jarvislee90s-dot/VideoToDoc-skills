"""图片命名格式测试（任务 6）。"""


def test_build_image_name_main() -> None:
    from videotodoc.slides import _build_image_name
    # 段 6, 段内第 2 个, capture @ 185.8s, 主图
    assert _build_image_name(seg_index=5, intra_index=1, capture_ms=185800, is_main=True) \
        == "p06_02_main_185.8s.png"


def test_build_image_name_candidate() -> None:
    from videotodoc.slides import _build_image_name
    # 段 12, 段内第 3 个, capture @ 449.1s, 候选
    assert _build_image_name(seg_index=11, intra_index=2, capture_ms=449100, is_main=False) \
        == "p12_03_449.1s.png"


def test_build_image_name_single_no_suffix() -> None:
    from videotodoc.slides import _build_image_name
    # 段 20, 段内第 1 个, 主图（单图时主图无 _main 后缀以保持简洁）
    result = _build_image_name(seg_index=19, intra_index=0, capture_ms=885220, is_main=True, single=True)
    assert result == "p20_01_885.2s.png"
