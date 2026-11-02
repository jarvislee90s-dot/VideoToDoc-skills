"""抖音源适配器。

抖音 web API 全部要求 a_bogus/msToken 实时签名，yt-dlp 的静态签名实现已被
风控 403（2026-08 实测）。因此本适配器不复用 yt-dlp，而是用 Playwright 打开
视频页，让页面自身的 JS 带完整签名调用 /aweme/v1/web/aweme/detail/，拦截响应
拿到 play_addr 直链（实测为音视频合流的渐进式 MP4，纯 HTTP 即可下载）。

登录态：持久化 profile（独立于日常浏览器），首次运行弹出有头窗口扫码一次，
之后 cookie 复用。无头失败（未登录/风控/验证码）自动升级有头重试。

支持输入：
    https://www.douyin.com/video/<id>
    https://v.douyin.com/<code>       （302 解析）
    文本中夹杂上述链接也可

不支持：图集 /note/、合集、直播（明确报错）。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

try:
    from .base import SourceVideo, normalize_url, slugify, source_cli_main
except ImportError:  # 独立 CLI 直跑时（python sources/douyin.py）无包上下文
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from base import SourceVideo, normalize_url, slugify, source_cli_main  # noqa: E402

DOUYIN_DOMAINS = ("douyin.com", "iesdouyin.com")
UNSUPPORTED_PATTERNS = (
    ("/note/", "图集（note）暂不支持，请提供视频链接 douyin.com/video/<id>"),
    ("/slides/", "合集（slides）暂不支持，请提供单视频链接"),
    ("/collection/", "合集暂不支持，请提供单视频链接"),
    ("/discover", "合集/专题页暂不支持，请提供单视频链接"),
)
DEFAULT_PROFILE_DIR = Path(os.environ.get(
    "VIDEO_SUMMARY_DOUYIN_PROFILE",
    str(Path.home() / "AppData" / "Local" / "VideoSkills" / "douyin-profile"),
))
DETAIL_API_MARK = "/aweme/v1/web/aweme/detail/"
# 无头模式默认 UA 带 HeadlessChrome 字样，会被抖音风控识别，统一伪装成正常 Chrome
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36")
LAUNCH_ARGS = ["--disable-blink-features=AutomationControlled"]


def matches(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    # 含裸域：用户粘贴 douyin.com/video/<id>（无 www）也必须命中，否则会静默
    # 落入 yt-dlp 通用路径——而该路径对抖音已被风控 403
    return any(host == d or host.endswith("." + d) for d in DOUYIN_DOMAINS)


def _parse_video_id(url: str) -> str | None:
    m = re.search(r"/video/(\d{15,20})", url)
    if m:
        return m.group(1)
    # 精选/搜索页的弹窗形态：douyin.com/jingxuan?modal_id=<id>
    m = re.search(r"[?&]modal_id=(\d{15,20})", url)
    return m.group(1) if m else None


def resolve_short_link(url: str) -> str:
    """v.douyin.com 短链 302 解析为 www.douyin.com/video/<id>。"""
    import urllib.request

    if _parse_video_id(url):
        return url
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.geturl()


def check_supported(url: str) -> None:
    """不支持的页面类型直接报错，避免静默产出错误内容。"""
    for pattern, msg in UNSUPPORTED_PATTERNS:
        if pattern in url:
            raise ValueError(msg)
    if not _parse_video_id(url):
        raise ValueError("未能从链接解析出视频 ID，请提供 douyin.com/video/<id> 形式的链接")


# ── Playwright 拦截下载 ─────────────────────────────────────


def _capture_detail(page, video_url: str, wait_seconds: int) -> dict | None:
    """打开视频页并拦截 detail API 的 JSON 响应。签名是一次性的，必须实时捕获。"""
    captured: dict | None = None

    def on_response(resp):
        nonlocal captured
        if captured is not None:
            return
        if DETAIL_API_MARK not in resp.url or resp.status != 200:
            return
        try:
            if "json" not in (resp.headers.get("content-type") or ""):
                return
            data = resp.json()
            if isinstance(data, dict) and data.get("aweme_detail"):
                captured = data
        except Exception:
            pass

    page.on("response", on_response)
    try:
        try:
            page.goto(video_url, wait_until="domcontentloaded", timeout=60_000)
        except Exception as e:
            print(f"  ⚠️  页面加载失败（{e.__class__.__name__}），按捕获失败处理")
            return None
        deadline = time.time() + wait_seconds
        while captured is None and time.time() < deadline:
            page.wait_for_timeout(500)
    finally:
        page.remove_listener("response", on_response)
    return captured


def _extract_from_detail(detail: dict, video_id: str) -> dict:
    """从 detail JSON 提取元数据与合流直链。"""
    d = detail.get("aweme_detail") or {}
    video = d.get("video") or {}
    play_addr = (video.get("play_addr") or {}).get("url_list") or []
    if not play_addr:
        raise RuntimeError("detail 响应中没有 play_addr 直链（可能视频被删除或需特定权限）")
    desc_lines = (d.get("desc") or "").strip().splitlines()
    title = desc_lines[0].strip() if desc_lines else ""
    return {
        "title": title or video_id,
        "author": (d.get("author") or {}).get("nickname"),
        "duration_ms": d.get("duration"),
        "play_url": play_addr[0],
        "aweme_id": video_id,
    }


def _download_play_url(play_url: str, out_path: Path) -> None:
    """直链为带签名的 CDN 地址。实测需要 Chrome UA + 抖音 Referer，缺一返回 403。

    先写 .part 临时文件，校验尺寸完整后 rename——失败/断流不留半截文件，
    避免下游把残缺 MP4 当有效缓存复用。
    """
    import urllib.request

    headers = {"User-Agent": USER_AGENT, "Referer": "https://www.douyin.com/"}
    req = urllib.request.Request(play_url, headers=headers)
    part_path = out_path.with_suffix(out_path.suffix + ".part")
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp, open(part_path, "wb") as f:
                total = int(resp.headers.get("Content-Length") or 0)
                done = 0
                while True:
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        sys.stdout.write(f"\r  ⬇️  {done / 1048576:.1f} / {total / 1048576:.1f} MB")
                        sys.stdout.flush()
            print()
            if total and done != total:
                raise IOError(f"下载不完整：{done} / {total} 字节（服务端提前断流）")
            if done == 0:
                raise IOError("下载到 0 字节")
            part_path.replace(out_path)
            return
        except Exception as e:
            last_err = e
            part_path.unlink(missing_ok=True)
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"视频直链下载失败：{last_err}")


def _has_session_cookie(context) -> bool:
    for c in context.cookies("https://www.douyin.com"):
        if c.get("name") == "sessionid" and c.get("value"):
            return True
    return False


def _wait_for_login(context, page, max_seconds: int) -> bool:
    """有头窗口内等用户扫码登录，轮询 sessionid 出现。"""
    print("  🔐 未检测到抖音登录态，请在浏览器窗口中扫码登录（抖音APP 扫一扫）...")
    print("     窗口保持打开，登录成功后本脚本自动继续。")
    page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=60_000)
    deadline = time.time() + max_seconds
    while time.time() < deadline:
        if _has_session_cookie(context):
            print("  ✅ 登录成功，登录态已保存到本地 profile")
            return True
        time.sleep(2)
    return False


def _launch_kwargs(headless: bool) -> dict:
    return dict(
        user_agent=USER_AGENT, headless=headless,
        viewport={"width": 1380, "height": 900}, locale="zh-CN",
        args=LAUNCH_ARGS,
    )


def probe(url: str, *, headless: bool = True, login_max_wait: int = 180,
          capture_wait: int = 30, profile_dir: Path | None = None) -> SourceVideo:
    """打开视频页捕获 detail API，返回元数据与合流直链（不下载）。"""
    url = normalize_url(url)
    if not matches(url):
        raise ValueError(f"非抖音链接：{url}")
    url = resolve_short_link(url)
    check_supported(url)
    video_id = _parse_video_id(url)
    assert video_id
    # 短链/分享页可能落在移动版页面，不触发桌面版 detail API，统一规范化到桌面页
    page_url = f"https://www.douyin.com/video/{video_id}"

    profile = Path(profile_dir) if profile_dir else DEFAULT_PROFILE_DIR
    profile.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright

    result_meta: dict | None = None
    last_error: str | None = None

    with sync_playwright() as p:
        attempts: list[bool] = [True, False] if headless else [False]
        for hl in attempts:
            label = "无头" if hl else "有头"
            print(f"  🌐 启动浏览器（{label}模式）...")
            try:
                context = p.chromium.launch_persistent_context(
                    str(profile), **_launch_kwargs(hl))
            except Exception as e:
                raise RuntimeError(
                    f"浏览器启动失败（{e.__class__.__name__}）。若提示 profile 被占用，"
                    "请确认没有其他 douyin.py/process.py 抖音任务在运行（同一 profile 不支持并行）") from e
            try:
                if not _has_session_cookie(context):
                    if hl:
                        last_error = "无头模式下无登录态"
                        print(f"  ⚠️  {last_error}，升级有头扫码登录...")
                        continue
                    page = context.new_page()
                    if not _wait_for_login(context, page, login_max_wait):
                        raise RuntimeError("等待扫码登录超时，未获取登录态")
                    page.close()

                page = context.new_page()
                detail = _capture_detail(page, page_url, capture_wait)
                if not detail and not hl:
                    print("  💡 若浏览器窗口出现滑块验证，请手动完成后脚本继续等待")
                    detail = _capture_detail(page, page_url, capture_wait * 2)
                if not detail:
                    last_error = f"{'无头' if hl else '有头'}模式下 {capture_wait}s 未捕获 detail API 响应（可能触发风控）"
                    print(f"  ⚠️  {last_error}")
                    continue

                result_meta = _extract_from_detail(detail, video_id)
            finally:
                context.close()
            if result_meta:
                break

    if result_meta is None:
        raise RuntimeError(f"抖音解析失败：{last_error or '未知原因'}")

    return SourceVideo(
        video_path=Path(),  # probe 阶段尚无文件；play_url 暂存于 metadata
        title=result_meta["title"],
        source="douyin",
        author=result_meta["author"],
        duration_ms=result_meta["duration_ms"],
        has_subtitle=False,
        metadata={
            "aweme_id": video_id, "page_url": page_url, "play_url": result_meta["play_url"],
        },
    )


def download(meta: SourceVideo, run_dir: Path) -> SourceVideo:
    """用 probe 拿到的直链下载视频到 run_dir（直链有效期约 16 小时）。"""
    play_url = meta.metadata.get("play_url")
    if not play_url:
        raise ValueError("meta 中没有 play_url，请先调用 probe()")

    video_id = meta.metadata.get("aweme_id", "video")
    safe_title = slugify(meta.title) or video_id
    out_path = run_dir / f"{safe_title}.mp4"
    if not out_path.exists():
        print("  ⬇️  下载视频（合流直链）...")
        _download_play_url(play_url, out_path)
    else:
        print(f"  ✅ 视频已存在：{out_path.name}")

    return SourceVideo(
        video_path=out_path,
        title=meta.title,
        source="douyin",
        author=meta.author,
        duration_ms=meta.duration_ms,
        has_subtitle=False,
        metadata=meta.metadata,
    )


def fetch(url: str, run_dir: Path, *, headless: bool = True, login_max_wait: int = 180,
          capture_wait: int = 30, profile_dir: Path | None = None) -> SourceVideo:
    """便捷封装：probe + download，供独立 CLI 使用。"""
    meta = probe(url, headless=headless, login_max_wait=login_max_wait,
                 capture_wait=capture_wait, profile_dir=profile_dir)
    return download(meta, run_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description="抖音单视频下载（Playwright 拦截 detail API）")
    parser.add_argument("url", help="抖音视频链接（支持 v.douyin.com 短链）")
    parser.add_argument("--output", required=True, help="输出 mp4 路径（文件名决定最终命名）")
    parser.add_argument("--login", action="store_true", help="仅执行扫码登录并保存 profile 后退出")
    parser.add_argument("--headful", action="store_true", help="强制有头模式（默认无头优先）")
    parser.add_argument("--profile", default=None, help=f"自定义 profile 目录（默认 {DEFAULT_PROFILE_DIR}）")
    parser.add_argument("--timeout", type=int, default=30, help="detail API 捕获等待秒数（默认 30）")
    args = parser.parse_args()

    url = normalize_url(args.url)
    profile = Path(args.profile) if args.profile else DEFAULT_PROFILE_DIR

    from playwright.sync_api import sync_playwright

    if args.login:
        profile.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                str(profile), **_launch_kwargs(False))
            page = context.new_page()
            ok = _wait_for_login(context, page, 180)
            context.close()
            if not ok:
                sys.exit(2)
        return

    target = Path(args.output).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    result = fetch(url, target.parent, headless=not args.headful,
                   capture_wait=args.timeout, profile_dir=profile)
    if result.video_path.resolve() != target:
        os.replace(result.video_path, target)  # Windows 下 rename 目标存在会抛错，用 replace 覆盖
        result.video_path = target
    source_cli_main(result)


if __name__ == "__main__":
    main()
