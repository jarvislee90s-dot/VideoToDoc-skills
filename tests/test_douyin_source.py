"""sources/douyin.py 的单元测试：纯函数逻辑 + mock 网络的重试逻辑。

不真实启动浏览器、不访问网络、不下载：
- probe/download/fetch/playwright 路径不测；
- resolve_short_link 只测"已有视频 ID 直接返回"的免网络分支；
- _download_play_url 用 unittest.mock.patch 模拟 urlopen 的 403→成功序列。
"""

import urllib.error
from pathlib import Path
from unittest import mock

import pytest

from sources import douyin as douyin_source


VIDEO_ID_19 = "7123456789012345678"


# ── matches：douyin.com 各子域 YES，其他平台 NO ─────────────────


@pytest.mark.parametrize("url", [
    "https://www.douyin.com/video/7123456789012345678",
    "https://v.douyin.com/iAbCdEf/",
    "https://iesdouyin.com/share/video/7123456789012345678",
    "https://www.iesdouyin.com/share/video/7123456789012345678",
    "https://douyin.com/video/7123456789012345678",  # 裸域（无 www）：必须命中，否则静默落入 yt-dlp 403 路径
])
def test_matches_accepts_douyin_hosts(url):
    assert douyin_source.matches(url) is True


@pytest.mark.parametrize("url", [
    "https://www.bilibili.com/video/BV1xx411c7mD",
    "https://www.youtube.com/watch?v=abc",
    "https://notdouyin.com/video/1",
    "",
])
def test_matches_rejects_non_douyin_urls(url):
    assert douyin_source.matches(url) is False


# ── _parse_video_id ────────────────────────────────────────────


def test_parse_video_id_extracts_standard_19_digit_id():
    url = f"https://www.douyin.com/video/{VIDEO_ID_19}?previous_page=web_search"
    assert douyin_source._parse_video_id(url) == VIDEO_ID_19


def test_parse_video_id_returns_none_for_url_without_video_id():
    assert douyin_source._parse_video_id("https://www.douyin.com/discover") is None
    assert douyin_source._parse_video_id("https://www.douyin.com/note/7123456789012345678") is None
    assert douyin_source._parse_video_id(f"https://www.douyin.com/video/{VIDEO_ID_19[:3]}") is None


# ── check_supported：不支持类型明确报错，正常视频链接通过 ─────────


@pytest.mark.parametrize("path", [
    "/note/7123456789012345678",
    "/slides/7123456789012345678",
    "/collection/7123456789012345678",
    "/discover?modal_id=1",
])
def test_check_supported_rejects_unsupported_page_types_with_message(path):
    url = f"https://www.douyin.com{path}"
    with pytest.raises(ValueError, match="暂不支持"):
        douyin_source.check_supported(url)


def test_check_supported_rejects_url_without_video_id():
    with pytest.raises(ValueError, match="视频 ID"):
        douyin_source.check_supported("https://www.douyin.com/user/MS4wLjABAAAA")


def test_check_supported_accepts_standard_video_url():
    douyin_source.check_supported(f"https://www.douyin.com/video/{VIDEO_ID_19}")  # 不应抛异常


# ── resolve_short_link：已含视频 ID 的链接直接返回（不发网络请求） ──


def test_resolve_short_link_returns_url_unchanged_when_video_id_present():
    url = f"https://www.douyin.com/video/{VIDEO_ID_19}?x=1"
    with mock.patch("urllib.request.urlopen") as m_urlopen:
        assert douyin_source.resolve_short_link(url) == url
    m_urlopen.assert_not_called()


# ── _extract_from_detail：detail JSON 元数据与直链提取 ───────────


def _make_detail(**overrides) -> dict:
    detail = {
        "aweme_detail": {
            "desc": "第一行标题\n第二行说明\n第三行话题",
            "author": {"nickname": "测试UP主"},
            "duration": 58500,
            "video": {
                "play_addr": {
                    "url_list": ["https://v26-web.douyinvod.com/video/tos/cn/abc?mime_type=video_mp4"],
                },
            },
        },
    }
    for key, value in overrides.items():
        if value is None:
            detail["aweme_detail"].pop(key, None)
        else:
            detail["aweme_detail"][key] = value
    return detail


def test_extract_from_detail_pulls_title_author_duration_play_url():
    meta = douyin_source._extract_from_detail(_make_detail(), VIDEO_ID_19)
    assert meta["title"] == "第一行标题"  # desc 多行只取首行
    assert meta["author"] == "测试UP主"
    assert meta["duration_ms"] == 58500
    assert meta["play_url"] == "https://v26-web.douyinvod.com/video/tos/cn/abc?mime_type=video_mp4"
    assert meta["aweme_id"] == VIDEO_ID_19


def test_extract_from_detail_falls_back_to_video_id_when_desc_empty():
    meta = douyin_source._extract_from_detail(_make_detail(desc=None), VIDEO_ID_19)
    assert meta["title"] == VIDEO_ID_19


def test_extract_from_detail_author_is_none_when_author_missing():
    meta = douyin_source._extract_from_detail(_make_detail(author=None), VIDEO_ID_19)
    assert meta["author"] is None


def test_extract_from_detail_raises_when_play_addr_empty():
    detail = _make_detail(video={"play_addr": {"url_list": []}})
    with pytest.raises(RuntimeError, match="play_addr"):
        douyin_source._extract_from_detail(detail, VIDEO_ID_19)


# ── _download_play_url：mock urlopen 验证重试逻辑 ───────────────


class _FakeResponse:
    """模拟 urlopen 返回的上下文管理器响应。"""

    def __init__(self, chunks, headers=None):
        self._chunks = list(chunks)
        self.headers = headers or {}

    def read(self, _size):
        return self._chunks.pop(0) if self._chunks else b""

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def _http403():
    return urllib.error.HTTPError("http://cdn.douyinvod.com/x.mp4", 403, "Forbidden", None, None)


def test_download_play_url_retries_after_403_then_writes_file(tmp_path):
    out_path = tmp_path / "测试 视频.mp4"  # Windows 中文+空格路径
    fake = _FakeResponse([b"ab", b"cd"], {"Content-Length": "4"})
    with mock.patch("urllib.request.urlopen", side_effect=[_http403(), fake]) as m_urlopen, \
         mock.patch("time.sleep") as m_sleep:
        douyin_source._download_play_url("http://cdn.douyinvod.com/x.mp4", out_path)

    assert out_path.read_bytes() == b"abcd"
    assert m_urlopen.call_count == 2, "403 失败一次后应重试一次"
    assert m_sleep.called, "重试之间应有退避等待"


def test_download_play_url_gives_up_after_three_attempts(tmp_path):
    out_path = tmp_path / "never_written.mp4"
    with mock.patch("urllib.request.urlopen", side_effect=[_http403(), _http403(), _http403()]) as m_urlopen, \
         mock.patch("time.sleep"), \
         pytest.raises(RuntimeError, match="下载失败"):
        douyin_source._download_play_url("http://cdn.douyinvod.com/x.mp4", out_path)

    assert m_urlopen.call_count == 3, "最多尝试 3 次"
    assert not out_path.exists()


# ── download：标题非法字符清洗与断点复用（纯文件系统，无网络） ────


def test_download_sanitizes_title_and_skips_download_when_file_exists(tmp_path):
    # 标题含 ASCII 非法字符 ?，download 会清洗为 _ 并生成同名文件
    existing = tmp_path / "已存在_的视频.mp4"
    existing.write_bytes(b"mp4-bytes")
    meta = douyin_source.SourceVideo(
        video_path=Path(),
        title="已存在?的视频",
        source="douyin",
        metadata={"play_url": "http://cdn/x.mp4", "aweme_id": VIDEO_ID_19},
    )
    with mock.patch.object(douyin_source, "_download_play_url") as m_download, \
         mock.patch("builtins.print"):
        result = douyin_source.download(meta, tmp_path)

    assert result.video_path == existing, "清洗后同名文件已存在时应直接复用，不重新下载"
    m_download.assert_not_called()
    assert result.metadata["aweme_id"] == VIDEO_ID_19


def test_download_raises_when_meta_has_no_play_url(tmp_path):
    meta = douyin_source.SourceVideo(video_path=Path(), title="t", metadata={})
    with pytest.raises(ValueError, match="play_url"):
        douyin_source.download(meta, tmp_path)
