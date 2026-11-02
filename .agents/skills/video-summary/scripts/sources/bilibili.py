"""B站源适配器（yt-dlp 系形态）。

B站 playurl API 有 412 反爬与 v_voucher 风控，下载走 curl_cffi 指纹 cookies
策略链（自动 buvid → 浏览器登录态 cookies → yt-dlp 兜底）；字幕与信息获取
复用 yt_dlp_source 通用实现（B站字幕列表优先走 player/v2 API）。
"""

from __future__ import annotations

import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

try:
    from .base import run_cmd, slugify
    from . import yt_dlp_source
except ImportError:  # 独立直跑时无包上下文
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from base import run_cmd, slugify  # noqa: E402
    import yt_dlp_source  # noqa: E402

has_subtitles = True

BILIBILI_DOMAINS = ("bilibili.com", "b23.tv")


def matches(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return any(host == d or host.endswith("." + d) for d in BILIBILI_DOMAINS)


# ── 信息获取（B站优先走 player/v2 API 拿字幕列表） ──────────


def fetch_info(url: str, proxy: str | None = None) -> dict:
    """获取视频信息：优先 curl_cffi 提取标题 + player/v2 字幕列表，失败回退 yt-dlp。"""
    try:
        from curl_cffi import requests as _  # noqa: F401
        bvid, cid, title = _bilibili_extract_ids(url)
        if title:
            # 检查字幕（通过 player/v2 API）
            subtitles: dict = {}
            auto_captions: dict = {}
            if bvid and cid:
                try:
                    from curl_cffi import requests as cffi_requests
                    resp = cffi_requests.get(
                        "https://api.bilibili.com/x/player/v2",
                        params={"bvid": bvid, "cid": cid},
                        impersonate="chrome", timeout=15,
                    )
                    sub_data = resp.json().get("data", {}).get("subtitle", {})
                    for s in sub_data.get("subtitles", []):
                        lang = s.get("lan", "unknown")
                        subtitles.setdefault(lang, []).append({
                            "ext": "json",
                            "url": s.get("subtitle_url", ""),
                            "language_code": lang,
                            "name": s.get("lan_doc", lang),
                        })
                except Exception:
                    pass
            print(f"  📺 标题：{title}")
            print(f"  🔤 人工字幕：{list(subtitles.keys()) or '无'}")
            print(f"  🤖 自动字幕：{list(auto_captions.keys()) or '无'}")
            return {"title": title, "subtitles": subtitles, "automatic_captions": auto_captions}
    except Exception:
        pass  # fallback to yt-dlp

    return yt_dlp_source.fetch_info(url, proxy)


# 字幕下载与通用平台一致（yt-dlp writesubtitles）
fetch_subtitles = yt_dlp_source.fetch_subtitles


# ── 流地址获取策略（curl_cffi 绕 412 / v_voucher 风控） ─────


def _bilibili_detect_v_voucher(data: dict) -> bool:
    """检测 playurl 返回是否为 v_voucher 风控（无真实视频流）。"""
    if data.get("code") != 0:
        return False
    d = data.get("data", {})
    return "v_voucher" in d and "dash" not in d and "durl" not in d


def _bilibili_get_stream_urls_with_cookies(bvid: str, cid: str) -> tuple[str | None, str | None, bool]:
    """带 buvid cookies 调 playurl。返回 (video_url, audio_url, is_v_voucher)。"""
    from curl_cffi import requests as cffi_requests

    s = cffi_requests.Session(impersonate="chrome")
    # 注入 buvid cookies
    try:
        fr = s.get("https://api.bilibili.com/x/frontend/finger/spi", timeout=20).json()
        s.cookies.set("buvid3", fr["data"]["b_3"], domain=".bilibili.com")
        s.cookies.set("buvid4", fr["data"]["b_4"], domain=".bilibili.com")
    except Exception:
        pass
    s.get(f"https://www.bilibili.com/video/{bvid}", timeout=20)

    resp = s.get(
        "https://api.bilibili.com/x/player/wbi/playurl",
        params={"bvid": bvid, "cid": cid, "fnval": 4048, "fnver": 0, "fourk": 1, "qn": 80},
        timeout=30,
    )
    data = resp.json()
    if _bilibili_detect_v_voucher(data):
        return None, None, True
    if data.get("code") != 0:
        return None, None, False
    d = data["data"]
    if "dash" in d:
        dash = d["dash"]
        videos = dash.get("video", [])
        audios = dash.get("audio", [])
        best_video = max(videos, key=lambda v: v.get("height", 0) * v.get("width", 0)) if videos else None
        best_audio = audios[0] if audios else None
        v_url = best_video.get("baseUrl") or best_video.get("base_url") if best_video else None
        a_url = best_audio.get("baseUrl") or best_audio.get("base_url") if best_audio else None
        return v_url, a_url, False
    elif "durl" in d:
        durls = d["durl"]
        return (durls[0]["url"] if durls else None), None, False
    return None, None, False


def _load_browser_cookies(browser: str, domain: str = ".bilibili.com") -> dict[str, str]:
    """从浏览器读取指定 domain 的 cookies。

    browser 可选：chrome, firefox, safari, edge。
    未安装 browser_cookie3 时返回空字典。
    """
    try:
        import browser_cookie3
    except ImportError:
        print("  ⚠️  未安装 browser_cookie3，无法读取浏览器 cookies")
        return {}

    loaders = {
        "chrome": browser_cookie3.chrome,
        "firefox": browser_cookie3.firefox,
        "safari": browser_cookie3.safari,
        "edge": browser_cookie3.edge,
    }
    loader = loaders.get(browser.lower())
    if loader is None:
        print(f"  ⚠️  不支持的浏览器：{browser}，跳过浏览器 cookies")
        return {}

    try:
        cj = loader(domain_name=domain)
        return {c.name: c.value for c in cj}
    except Exception as e:
        print(f"  ⚠️  读取 {browser} cookies 失败：{e}")
        return {}


def _bilibili_get_stream_urls_with_browser_cookies(
    bvid: str, cid: str, browser: str
) -> tuple[str | None, str | None, bool]:
    """从浏览器读取登录态 cookies 调 B站 playurl。"""
    from curl_cffi import requests as cffi_requests

    cookies = _load_browser_cookies(browser)
    if not cookies:
        return None, None, False

    s = cffi_requests.Session(impersonate="chrome")
    for name, value in cookies.items():
        s.cookies.set(name, value, domain=".bilibili.com")

    s.get(f"https://www.bilibili.com/video/{bvid}", timeout=20)

    resp = s.get(
        "https://api.bilibili.com/x/player/wbi/playurl",
        params={"bvid": bvid, "cid": cid, "fnval": 4048, "fnver": 0, "fourk": 1, "qn": 80},
        timeout=30,
    )
    data = resp.json()
    if _bilibili_detect_v_voucher(data):
        return None, None, True
    if data.get("code") != 0:
        return None, None, False

    d = data["data"]
    if "dash" in d:
        dash = d["dash"]
        videos = dash.get("video", [])
        audios = dash.get("audio", [])
        best_video = max(videos, key=lambda v: v.get("height", 0) * v.get("width", 0)) if videos else None
        best_audio = audios[0] if audios else None
        v_url = best_video.get("baseUrl") or best_video.get("base_url") if best_video else None
        a_url = best_audio.get("baseUrl") or best_audio.get("base_url") if best_audio else None
        return v_url, a_url, False
    elif "durl" in d:
        durls = d["durl"]
        return (durls[0]["url"] if durls else None), None, False
    return None, None, False


def _bilibili_get_stream_urls(bvid: str, cid: str) -> tuple[str | None, str | None]:
    """通过 curl_cffi 直接调用 B站 playurl API 获取视频/音频流 URL
    返回 (video_url, audio_url)，DASH 格式分离
    """
    from curl_cffi import requests as cffi_requests

    resp = cffi_requests.get(
        "https://api.bilibili.com/x/player/wbi/playurl",
        params={"bvid": bvid, "cid": cid, "fnval": 4048, "fnver": 0, "fourk": 1, "qn": 80},
        impersonate="chrome",
        timeout=30,
    )
    data = resp.json()
    if data.get("code") != 0:
        return None, None

    d = data["data"]
    if "dash" in d:
        dash = d["dash"]
        videos = dash.get("video", [])
        audios = dash.get("audio", [])
        # 选最高画质的视频
        best_video = max(videos, key=lambda v: v.get("height", 0) * v.get("width", 0)) if videos else None
        best_audio = audios[0] if audios else None
        v_url = best_video.get("baseUrl") or best_video.get("base_url") if best_video else None
        a_url = best_audio.get("baseUrl") or best_audio.get("base_url") if best_audio else None
        return v_url, a_url
    elif "durl" in d:
        durls = d["durl"]
        return durls[0]["url"] if durls else None, None
    return None, None


def _bilibili_extract_ids(url: str) -> tuple[str | None, str | None, str | None]:
    """从 B站 URL 或页面提取 (bvid, cid, title)"""
    from curl_cffi import requests as cffi_requests

    bvid_match = re.search(r"(BV[a-zA-Z0-9]+)", url)
    bvid = bvid_match.group(1) if bvid_match else None

    resp = cffi_requests.get(url, impersonate="chrome", timeout=30)
    if resp.status_code != 200:
        return bvid, None, None

    cid_match = re.search(r'"cid":(\d+)', resp.text)
    cid = cid_match.group(1) if cid_match else None

    title_match = re.search(r"<title[^>]*>(.*?)</title>", resp.text, re.DOTALL)
    title = title_match.group(1).strip() if title_match else None
    if title:
        title = re.sub(r"_哔哩哔哩_bilibili$", "", title).strip()

    return bvid, cid, title


def _download_stream(url: str, tmp_path: Path, headers: dict) -> None:
    from curl_cffi import requests as cffi_requests
    r = cffi_requests.get(url, headers=headers, impersonate="chrome", timeout=120, stream=True)
    try:
        with open(tmp_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                f.write(chunk)
    finally:
        r.close()


def _bilibili_download(url: str, run_dir: Path, title: str | None = None,
                       stream_urls: tuple[str | None, str | None] | None = None) -> Path:
    """B站视频下载（curl_cffi 绕过 412），支持 DASH 和直链。

    stream_urls: 已获取的 (video_url, audio_url)，避免重复请求 playurl。
    """
    bvid, cid, extracted_title = _bilibili_extract_ids(url)
    if not bvid or not cid:
        raise RuntimeError("无法从 B站 URL 提取 bvid/cid")

    # 优先使用传入的标题，否则使用提取的标题
    title = title or extracted_title or "video"
    safe_title = slugify(title)

    print(f"  📺 B站 BVID={bvid} CID={cid} 标题={title}")
    if stream_urls:
        v_url, a_url = stream_urls
    else:
        v_url, a_url = _bilibili_get_stream_urls(bvid, cid)
    if not v_url:
        raise RuntimeError("B站 playurl API 未返回视频流")

    headers = {"Referer": "https://www.bilibili.com", "User-Agent": "Mozilla/5.0"}

    if a_url:
        # DASH：分别下载视频和音频，合并（并行下载）
        v_tmp = run_dir / f"_{safe_title}_video_only.m4s"
        a_tmp = run_dir / f"_{safe_title}_audio_only.m4s"
        out_path = run_dir / f"{safe_title}.mp4"

        print(f"  ⬇️  并行下载音视频流...")
        with ThreadPoolExecutor(max_workers=2) as executor:
            f_video = executor.submit(_download_stream, v_url, v_tmp, headers)
            f_audio = executor.submit(_download_stream, a_url, a_tmp, headers)
            f_video.result()
            f_audio.result()

        print(f"  🔀 合并音视频...")
        run_cmd(["ffmpeg", "-y", "-i", str(v_tmp), "-i", str(a_tmp),
                 "-c:v", "copy", "-c:a", "copy", "-movflags", "+faststart",
                 str(out_path)], timeout=120)
        v_tmp.unlink(missing_ok=True)
        a_tmp.unlink(missing_ok=True)
        return out_path
    else:
        # 直链
        out_path = run_dir / f"{safe_title}.mp4"
        print(f"  ⬇️  下载视频...")
        _download_stream(v_url, out_path, headers)
        return out_path


# ── 适配器入口（原 process.download_video 的 B站策略链） ────


def download(url: str, run_dir: Path, title: str | None = None, proxy: str | None = None,
             cookies_from_browser: str | None = None) -> Path:
    """B站下载策略链：curl_cffi buvid → 浏览器 cookies → yt-dlp 兜底。"""
    try:
        from curl_cffi import requests as _  # noqa: F401
        print("  ⬇️  下载视频（curl_cffi 模式，策略1：buvid cookies）...")
        bvid, cid, _ = _bilibili_extract_ids(url)
        v_url, a_url, is_v_voucher = _bilibili_get_stream_urls_with_cookies(bvid, cid)
        if is_v_voucher:
            print("  ⚠️  B站 v_voucher 风控，未登录态无法获取视频流")
            if cookies_from_browser:
                print(f"  💡  策略2：使用 {cookies_from_browser} 浏览器 cookies 重试...")
                v_url2, a_url2, is_v2 = _bilibili_get_stream_urls_with_browser_cookies(bvid, cid, cookies_from_browser)
                if not is_v2 and v_url2:
                    return _bilibili_download(url, run_dir, title, stream_urls=(v_url2, a_url2))
                print(f"  ⚠️  curl_cffi 带cookies仍触发v_voucher，回退到 yt-dlp（使用浏览器cookies）...")
            else:
                print("  ❌  该视频触发B站风控，需登录态。回退到 yt-dlp 尝试...")
        if v_url and not is_v_voucher:
            # 复用已获取的流 URL，不再重复请求 playurl
            return _bilibili_download(url, run_dir, title, stream_urls=(v_url, a_url))
        print("  ⚠️  curl_cffi 未获取视频流，回退到 yt-dlp...")
    except Exception as e:
        print(f"  ⚠️  curl_cffi 下载失败（{e}），回退到 yt-dlp...")

    return yt_dlp_source.download(url, run_dir, title, proxy, cookies_from_browser)
