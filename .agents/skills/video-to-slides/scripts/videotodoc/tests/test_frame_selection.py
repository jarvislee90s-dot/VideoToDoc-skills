from videotodoc.config import Settings


def test_settings_has_frame_drift_back_seconds():
    s = Settings()
    assert hasattr(s, "frame_drift_back_seconds")
    assert s.frame_drift_back_seconds == 2.0


def test_settings_has_min_edge_density():
    s = Settings()
    assert hasattr(s, "min_edge_density")
    assert s.min_edge_density == 0.02
