from videotodoc.segment import capture_interval_for_duration


class TestCaptureInterval:
    def test_short_video_5min(self):
        assert capture_interval_for_duration(300) == 15

    def test_15min_video(self):
        assert capture_interval_for_duration(900) == 20

    def test_30min_video(self):
        assert capture_interval_for_duration(1800) == 30

    def test_long_video_over_30min(self):
        assert capture_interval_for_duration(3600) == 40

    def test_boundary_5min(self):
        assert capture_interval_for_duration(301) == 20

    def test_boundary_15min(self):
        assert capture_interval_for_duration(901) == 30

    def test_boundary_30min(self):
        assert capture_interval_for_duration(1801) == 40
