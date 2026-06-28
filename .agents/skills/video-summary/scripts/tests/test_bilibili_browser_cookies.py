from unittest.mock import MagicMock, patch


def test_load_browser_cookies_returns_dict():
    """_load_browser_cookies 应返回浏览器 cookie 字典。"""
    import sys
    sys.path.insert(0, "/Users/jarvis/Documents/VideoToDoc-skills/.agents/skills/video-summary/scripts")
    from process import _load_browser_cookies

    mock_cookie = MagicMock()
    mock_cookie.name = "SESSDATA"
    mock_cookie.value = "abc123"
    mock_cookie.domain = ".bilibili.com"

    with patch("browser_cookie3.chrome", return_value=[mock_cookie]):
        cookies = _load_browser_cookies("chrome")

    assert cookies.get("SESSDATA") == "abc123"


def test_bilibili_get_stream_urls_with_browser_cookies_uses_browser_cookie(monkeypatch):
    """_bilibili_get_stream_urls_with_browser_cookies 应把浏览器 cookie 注入 curl_cffi session。"""
    import sys
    sys.path.insert(0, "/Users/jarvis/Documents/VideoToDoc-skills/.agents/skills/video-summary/scripts")
    from process import _bilibili_get_stream_urls_with_browser_cookies

    captured_cookies = {}

    class FakeCookies:
        def set(self, name, value, domain=None):
            captured_cookies[name] = (value, domain)

    class FakeSession:
        def __init__(self, *args, **kwargs):
            self.cookies = FakeCookies()

        def get(self, url, timeout=20, **kwargs):
            resp = MagicMock()
            resp.json.return_value = {"code": -1}
            return resp

    monkeypatch.setattr("curl_cffi.requests.Session", FakeSession)
    monkeypatch.setattr("process._load_browser_cookies", lambda b: {"SESSDATA": "abc123"})

    _bilibili_get_stream_urls_with_browser_cookies("BV1xx", "12345", "chrome")
    assert captured_cookies.get("SESSDATA") == ("abc123", ".bilibili.com")
