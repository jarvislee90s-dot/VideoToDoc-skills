import importlib.util
from pathlib import Path

# 显式从 video-summary/scripts/process.py 加载，避免与 video-to-slides/scripts/process.py 冲突
_VS_PROCESS = Path(__file__).resolve().parents[4] / "video-summary" / "scripts" / "process.py"
_spec = importlib.util.spec_from_file_location("vs_process", _VS_PROCESS)
vs_process = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vs_process)


class TestBilibiliRiskControl:
    def test_detect_v_voucher_present(self):
        data = {"code": 0, "data": {"v_voucher": "voucher_abc"}}
        assert vs_process._bilibili_detect_v_voucher(data) is True

    def test_detect_v_voucher_absent_with_dash(self):
        data = {"code": 0, "data": {"dash": {"video": [], "audio": []}}}
        assert vs_process._bilibili_detect_v_voucher(data) is False

    def test_detect_v_voucher_error_code(self):
        data = {"code": -404, "message": "不存在"}
        assert vs_process._bilibili_detect_v_voucher(data) is False
