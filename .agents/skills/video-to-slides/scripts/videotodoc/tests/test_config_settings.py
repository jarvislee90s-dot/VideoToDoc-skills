"""Settings 新增字段默认值测试（任务 1）。"""


def test_settings_new_fields_defaults() -> None:
    from videotodoc.config import Settings

    s = Settings()
    # 4.1 节：detect 阶段严格度参数
    assert s.scene_threshold == 0.06
    assert s.min_slide_seconds == 1.0
    assert s.max_candidates == 200
    # 4.2 节：匹配窗口
    assert s.match_window_sec is None
    # 4.4 节：段内多候选
    assert s.keep_all_segment_candidates is False
    # 4.5 节：主图评分权重
    assert s.main_score_edge_weight == 0.5
    assert s.main_score_ocr_weight == 0.5
    # 4.8 节：opencv 截图
    assert s.use_opencv_capture is True
    assert s.detect_workers == 8
