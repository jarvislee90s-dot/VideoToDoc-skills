"""sources/ 源适配器注册与派发的单元测试（第二阶段重构）。

覆盖：matches 识别、process._find_adapter 注册表派发、process.download_video 分发、
B站 v_voucher 风控检测与下载策略链。全部 mock 或纯函数，不访问网络、
不读浏览器 cookies、不真实下载。

加载方式：tests/conftest.py 已把 video-summary/scripts 前置到 sys.path，
`from sources import ...` 命中本技能模块；video-summary 的 process 一律经
vs_process 夹具获取（`import process` 在全量回归中会被 video-to-slides
的同名 process.py 污染，详见 conftest 注释）。
"""

import sys
from pathlib import Path
from unittest import mock

import pytest

from sources import bilibili, youtube, yt_dlp_source  # noqa: E402  conftest 已注入 sys.path


# ── 模块解析安全网：同名 process.py 冲突防护 ──────────────────


def test_vs_process_fixture_loads_video_summary_copy(vs_process):
    """夹具加载的必须是 video-summary 的 process.py，而非 video-to-slides 同名模块。"""
    assert "video-summary" in Path(vs_process.__file__).resolve().as_posix()


def test_process_compat_reexports_point_to_sources_implementations(vs_process):
    """process 兼容导出必须指向 sources 真身（video-to-slides 以 vs_process._parse_subtitle_file 引用）。"""
    assert vs_process._load_browser_cookies is bilibili._load_browser_cookies
    assert vs_process._bilibili_detect_v_voucher is bilibili._bilibili_detect_v_voucher
    assert vs_process._parse_subtitle_file is yt_dlp_source._parse_subtitle_file


# ── matches：URL 识别（纯函数） ───────────────────────────────


@pytest.mark.parametrize("url", [
    "https://www.bilibili.com/video/BV1xx411c7mD",
    "https://b23.tv/iAbCdEf/",
    "https://m.bilibili.com/video/BV1xx411c7mD",
])
def test_bilibili_matches_accepts_bilibili_hosts(url):
    assert bilibili.matches(url) is True


@pytest.mark.parametrize("url", [
    "https://notbilibili.com/video/BV1xx411c7mD",  # endswith(".bilibili.com") 不应误命中
    "https://www.douyin.com/video/7123456789012345678",
    "",
])
def test_bilibili_matches_rejects_non_bilibili_urls(url):
    assert bilibili.matches(url) is False


@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=abc",
    "https://youtube.com/watch?v=abc",
    "https://youtu.be/abc",
    "https://music.youtube.com/watch?v=abc",
    "https://youtube-nocookie.com/embed/abc",
])
def test_youtube_matches_accepts_youtube_hosts(url):
    assert youtube.matches(url) is True


@pytest.mark.parametrize("url", [
    "https://notyoutube.com/watch?v=abc",  # removeprefix("www.") 后仍不得误命中
    "https://www.bilibili.com/video/BV1xx411c7mD",
    "",
])
def test_youtube_matches_rejects_non_youtube_urls(url):
    assert youtube.matches(url) is False


@pytest.mark.parametrize("url", [
    "https://www.bilibili.com/video/BV1xx411c7mD",
    "https://vimeo.com/123456",
    "https://www.xiaohongshu.com/explore/abc",
    "",
])
def test_yt_dlp_source_matches_accepts_any_url_as_fallback(url):
    """yt_dlp_source 是注册表末位的兜底适配器：任意 URL 都接受。"""
    assert yt_dlp_source.matches(url) is True


# ── process._find_adapter：注册表派发 ─────────────────────────


def test_find_adapter_dispatches_douyin_url_to_douyin_module(vs_process):
    adapter = vs_process._find_adapter("https://www.douyin.com/video/7123456789012345678")
    assert adapter is not None
    assert adapter.__name__ == "sources.douyin"


def test_find_adapter_dispatches_bilibili_url_to_bilibili_module(vs_process):
    adapter = vs_process._find_adapter("https://www.bilibili.com/video/BV1xx411c7mD")
    assert adapter is not None
    assert adapter.__name__ == "sources.bilibili"


def test_find_adapter_dispatches_youtube_url_to_youtube_module(vs_process):
    adapter = vs_process._find_adapter("https://www.youtube.com/watch?v=abc")
    assert adapter is not None
    assert adapter.__name__ == "sources.youtube"


def test_find_adapter_returns_none_for_unregistered_platform(vs_process):
    """小红书未注册适配器：返回 None（后续由通用 yt-dlp 兜底），不得误派发。"""
    assert vs_process._find_adapter("https://www.xiaohongshu.com/explore/abc") is None
    assert vs_process._find_adapter("https://xhslink.com/abc") is None


def test_get_douyin_adapter_finds_independent_downloader_form(vs_process):
    """独立下载器形态识别：douyin 有 probe 且 has_subtitles=False，必须被 _get_douyin_adapter 命中，
    否则 cmd_process 对抖音 URL 一律 SystemExit（'缺少抖音适配器'）。"""
    adapter = vs_process._get_douyin_adapter()
    assert adapter is not None
    assert adapter.__name__ == "sources.douyin"
    assert adapter.has_subtitles is False


# ── bilibili._bilibili_detect_v_voucher：风控响应识别 ──────────


@pytest.mark.parametrize("data,expected", [
    ({"code": 0, "data": {"v_voucher": "risk"}}, True),   # 仅 v_voucher、无真实流 → 风控
    ({"code": 0, "data": {"v_voucher": "risk", "dash": {"video": []}}}, False),  # 有 dash → 真实流
    ({"code": 0, "data": {"v_voucher": "risk", "durl": [{"url": "x"}]}}, False),  # 有 durl → 真实流
    ({"code": -404, "data": {"v_voucher": "risk"}}, False),  # code≠0 → 非风控形态
    ({"code": 0, "data": {}}, False),  # 无 v_voucher → 非风控
    ({"code": 0}, False),  # 缺 data 键 → 非风控
])
def test_detect_v_voucher_only_when_no_real_stream_present(data, expected):
    assert bilibili._bilibili_detect_v_voucher(data) is expected


# ── bilibili.download：策略链（全部 mock，不触网） ─────────────


def test_download_uses_browser_cookie_strategy2_when_v_voucher(tmp_path):
    """策略1 触发 v_voucher + 提供浏览器来源 → 走策略2，命中流后调 _bilibili_download。"""
    fake_out = tmp_path / "out.mp4"
    url = "https://www.bilibili.com/video/BV1xx411c7mD"
    with mock.patch.object(bilibili, "_bilibili_extract_ids", return_value=("BV1xx411c7mD", "123", "标题")), \
         mock.patch.object(bilibili, "_bilibili_get_stream_urls_with_cookies",
                           return_value=(None, None, True)) as m_strategy1, \
         mock.patch.object(bilibili, "_bilibili_get_stream_urls_with_browser_cookies",
                           return_value=("http://video", "http://audio", False)) as m_strategy2, \
         mock.patch.object(bilibili, "_bilibili_download", return_value=fake_out) as m_download, \
         mock.patch.object(yt_dlp_source, "download") as m_yt_dlp:
        result = bilibili.download(url, tmp_path, title="标题", cookies_from_browser="chrome")

    assert result == fake_out
    m_strategy1.assert_called_once_with("BV1xx411c7mD", "123")
    m_strategy2.assert_called_once_with("BV1xx411c7mD", "123", "chrome")
    m_download.assert_called_once_with(url, tmp_path, "标题",
                                       stream_urls=("http://video", "http://audio"))
    # 策略2 成功后不应再走 yt-dlp 兜底
    m_yt_dlp.assert_not_called()


def test_download_uses_strategy1_stream_urls_without_risk_control(tmp_path):
    """策略1 直接拿到流 → 复用流 URL 下载，不读浏览器 cookies。"""
    fake_out = tmp_path / "out.mp4"
    url = "https://www.bilibili.com/video/BV1xx411c7mD"
    with mock.patch.object(bilibili, "_bilibili_extract_ids", return_value=("BV1xx411c7mD", "123", "标题")), \
         mock.patch.object(bilibili, "_bilibili_get_stream_urls_with_cookies",
                           return_value=("http://v1", "http://a1", False)) as m_strategy1, \
         mock.patch.object(bilibili, "_bilibili_get_stream_urls_with_browser_cookies") as m_strategy2, \
         mock.patch.object(bilibili, "_bilibili_download", return_value=fake_out) as m_download, \
         mock.patch.object(yt_dlp_source, "download") as m_yt_dlp:
        result = bilibili.download(url, tmp_path, title="标题", cookies_from_browser="chrome")

    assert result == fake_out
    m_download.assert_called_once_with(url, tmp_path, "标题",
                                       stream_urls=("http://v1", "http://a1"))
    # 未触发风控不应读浏览器 cookies
    m_strategy2.assert_not_called()
    m_yt_dlp.assert_not_called()


def test_download_falls_back_to_yt_dlp_when_v_voucher_and_no_browser_cookies(tmp_path):
    """策略1 触发 v_voucher 且未提供浏览器来源 → 直接回退 yt-dlp（透传 cookies_from_browser）。"""
    fake_out = tmp_path / "out.mp4"
    url = "https://www.bilibili.com/video/BV1xx411c7mD"
    with mock.patch.object(bilibili, "_bilibili_extract_ids", return_value=("BV1xx411c7mD", "123", "标题")), \
         mock.patch.object(bilibili, "_bilibili_get_stream_urls_with_cookies",
                           return_value=(None, None, True)), \
         mock.patch.object(bilibili, "_bilibili_get_stream_urls_with_browser_cookies") as m_strategy2, \
         mock.patch.object(bilibili, "_bilibili_download") as m_download, \
         mock.patch.object(yt_dlp_source, "download", return_value=fake_out) as m_yt_dlp:
        result = bilibili.download(url, tmp_path, title="标题")

    assert result == fake_out
    m_strategy2.assert_not_called()
    m_download.assert_not_called()
    m_yt_dlp.assert_called_once_with(url, tmp_path, "标题", None, None)


def test_download_falls_back_to_yt_dlp_when_curl_cffi_missing(tmp_path):
    """curl_cffi 缺失（import 抛 ImportError）→ 整条 curl_cffi 策略链跳过，回退 yt-dlp。"""
    fake_out = tmp_path / "out.mp4"
    url = "https://www.bilibili.com/video/BV1xx411c7mD"
    with mock.patch.dict(sys.modules, {"curl_cffi": None}), \
         mock.patch.object(bilibili, "_bilibili_download") as m_download, \
         mock.patch.object(yt_dlp_source, "download", return_value=fake_out) as m_yt_dlp:
        result = bilibili.download(url, tmp_path, title="标题", proxy=None,
                                   cookies_from_browser="chrome")

    assert result == fake_out
    m_download.assert_not_called()
    m_yt_dlp.assert_called_once_with(url, tmp_path, "标题", None, "chrome")


# ── process.download_video：按 URL 派发 ───────────────────────


def test_download_video_dispatches_bilibili_url_to_bilibili_adapter(tmp_path, vs_process):
    fake_out = tmp_path / "b.mp4"
    url = "https://www.bilibili.com/video/BV1xx411c7mD"
    with mock.patch("sources.bilibili.download", return_value=fake_out) as m_bilibili, \
         mock.patch("sources.yt_dlp_source.download") as m_yt_dlp:
        result = vs_process.download_video(url, tmp_path, "标题")

    assert result == fake_out
    m_bilibili.assert_called_once_with(url, tmp_path, "标题", None, None)
    m_yt_dlp.assert_not_called()


def test_download_video_dispatches_youtube_url_to_youtube_adapter(tmp_path, vs_process):
    fake_out = tmp_path / "y.mp4"
    url = "https://www.youtube.com/watch?v=abc"
    with mock.patch("sources.youtube.download", return_value=fake_out) as m_youtube:
        result = vs_process.download_video(url, tmp_path, "t")

    assert result == fake_out
    m_youtube.assert_called_once_with(url, tmp_path, "t", None, None)


def test_download_video_dispatches_unregistered_url_to_yt_dlp_fallback(tmp_path, vs_process):
    """注册表未命中（如 vimeo）→ 通用 yt_dlp_source.download 兜底。"""
    fake_out = tmp_path / "g.mp4"
    url = "https://vimeo.com/123456789"
    with mock.patch("sources.bilibili.download") as m_bilibili, \
         mock.patch("sources.yt_dlp_source.download", return_value=fake_out) as m_yt_dlp:
        result = vs_process.download_video(url, tmp_path)

    assert result == fake_out
    m_bilibili.assert_not_called()
    m_yt_dlp.assert_called_once_with(url, tmp_path, None, None, None)


def test_download_video_skips_douyin_adapter_via_has_subtitles_guard(tmp_path, vs_process):
    """抖音是独立下载器形态（has_subtitles=False）：download_video 不得走它的 download，
    应落回通用 yt-dlp（抖音真实下载在 cmd_process 的 probe/download 路径）。"""
    fake_out = tmp_path / "d.mp4"
    url = "https://www.douyin.com/video/7123456789012345678"
    with mock.patch("sources.douyin.download") as m_douyin, \
         mock.patch("sources.yt_dlp_source.download", return_value=fake_out) as m_yt_dlp:
        result = vs_process.download_video(url, tmp_path)

    assert result == fake_out
    # has_subtitles=False 的适配器不应被 download_video 选用
    m_douyin.assert_not_called()
    m_yt_dlp.assert_called_once()
