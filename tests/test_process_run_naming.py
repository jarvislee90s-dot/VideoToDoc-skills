"""process.py 命名纯函数的单元测试（_slugify / _build_run_dir_name）。

只调用纯函数并在 tmp_path 内做真实 mkdir 验证，不起浏览器、不访问网络。

加载方式说明：video-to-slides/scripts 下存在同名 process.py，且 pytest.ini 的
pythonpath 使其可被 `import process` 命中。为避免 sys.modules 命名冲突，
这里用 importlib 以独立模块名从绝对路径加载 video-summary 的 process.py。
"""

import importlib.util
import re
from pathlib import Path
from unittest import mock

PROCESS_PATH = (
    Path(__file__).resolve().parents[1]
    / ".agents" / "skills" / "video-summary" / "scripts" / "process.py"
)
_spec = importlib.util.spec_from_file_location("video_summary_process", PROCESS_PATH)
process = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(process)

WINDOWS_FORBIDDEN = '<>:"/\\|?*'


# ── _slugify：抖音典型标题字符的鲁棒性 ─────────────────────────


def test_slugify_replaces_ascii_filename_forbidden_chars():
    assert process._slugify('a/b:c?d*e"f<g|h>i') == "a_b_c_d_e_f_g_h_i"


def test_slugify_keeps_cjk_emoji_hash_and_fullwidth_punct():
    # 全角 ？、#、emoji 都是 Windows 文件名的合法字符，应原样保留
    assert process._slugify("什么是确定性？🎉") == "什么是确定性？🎉"
    assert process._slugify("#名场面合集") == "#名场面合集"


def test_slugify_falls_back_to_video_when_result_empty():
    assert process._slugify("") == "video"
    assert process._slugify("\x00\x1f*") == "video", "控制字符与 * 全被替换后应回退为 video"


def test_slugify_caps_title_length_at_80():
    slug = process._slugify("长" * 100)
    assert len(slug) == 80


def test_slugify_douyin_style_title_has_no_windows_forbidden_chars():
    slug = process._slugify("高能🎉#片段?测试？")
    assert not any(ch in slug for ch in WINDOWS_FORBIDDEN)


# ── _build_run_dir_name：标题_时间戳 ──────────────────────────


def test_build_run_dir_name_appends_yyyymmdd_hhmmss_timestamp():
    title = "高能🎉#片段?测试？"
    with mock.patch.object(process, "_timestamp", return_value="20261102_120000"):
        name = process._build_run_dir_name(title, "https://v.douyin.com/iAbCdEf/")
    assert name == f"{process._slugify(title)}_20261102_120000"


def test_build_run_dir_name_is_creatable_on_filesystem_for_douyin_title(tmp_path):
    name = process._build_run_dir_name("高能🎉#片段?测试？", "https://www.douyin.com/video/7123456789012345678")
    ts_part = name.rsplit("_", 2)[-2] + "_" + name.rsplit("_", 1)[-1]
    assert re.fullmatch(r"\d{8}_\d{6}", ts_part), f"尾部应为时间戳，实际：{name}"
    assert not any(ch in name for ch in WINDOWS_FORBIDDEN), f"目录名含 Windows 非法字符：{name}"
    (tmp_path / name).mkdir()  # 真实建目录验证（含 emoji/#/全角？的路径）


def test_build_run_dir_name_works_with_title_containing_path_separators(tmp_path):
    name = process._build_run_dir_name("a/b:c", "ignored")
    assert re.fullmatch(r"a_b_c_\d{8}_\d{6}", name), f"路径分隔符应被替换为下划线，实际：{name}"
    (tmp_path / name).mkdir()
