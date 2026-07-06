"""video-type 自动分类：按场景变化率/边缘密度/饱和度判型。"""
from videotodoc.slides import _classify_by_features, VideoType


class TestClassifyByFeatures:
    def test_lecture_slides_low_scene_high_edge(self):
        # 场景变化少 + 边缘密度高（PPT 文字多）→ lecture_slides
        assert _classify_by_features(scene_rate=0.02, edge_density=0.20, saturation_mean=50) == "lecture_slides"

    def test_talking_head_low_scene_low_edge_low_sat(self):
        # 场景几乎不变 + 边缘少 + 饱和度低（出镜讲解）→ talking_head
        assert _classify_by_features(scene_rate=0.01, edge_density=0.05, saturation_mean=40) == "talking_head"

    def test_screen_recording_mid_scene_high_edge(self):
        assert _classify_by_features(scene_rate=0.06, edge_density=0.25, saturation_mean=70) == "screen_recording"

    def test_movie_cinematic_high_scene(self):
        assert _classify_by_features(scene_rate=0.40, edge_density=0.10, saturation_mean=60) == "movie_cinematic"

    def test_tutorial_fallback(self):
        # 不满足任何特殊条件 → tutorial
        assert _classify_by_features(scene_rate=0.15, edge_density=0.12, saturation_mean=100) == "tutorial"

    def test_video_type_values(self):
        for t in VideoType.__args__:
            assert isinstance(t, str)


class TestSceneThresholdByType:
    def test_talking_head_uses_loose_threshold(self):
        from videotodoc.slides import _scene_threshold_for_type
        assert _scene_threshold_for_type("talking_head", base=0.06) == 0.20

    def test_lecture_slides_uses_sensitive_threshold(self):
        from videotodoc.slides import _scene_threshold_for_type
        assert _scene_threshold_for_type("lecture_slides", base=0.06) == 0.03

    def test_auto_keeps_base(self):
        from videotodoc.slides import _scene_threshold_for_type
        assert _scene_threshold_for_type("auto", base=0.06) == 0.06
