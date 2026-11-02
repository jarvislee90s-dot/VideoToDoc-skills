#!/usr/bin/env python3
"""video-summary: 视频 URL 或本地文件 → 下载 + 字幕/ASR → 摘要

流程：
  URL  → 获取字幕（优先）→ 有字幕直接保存 → 无字幕下载视频 → ASR
  本地 → 提取音频 → ASR → transcript.txt

产物命名：
  runs/<视频标题>_<时间戳>/
    ├── <视频标题>_总结_<时间戳>.md   # 最终摘要
    ├── transcript.json
    ├── transcript.txt
    └── video.mp4（如需ASR）
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# 源适配器：每个平台一个独立模块（scripts/sources/），风控变化时只改对应模块。
# 延迟加载：sources/ 缺失（单技能分包分发）时不影响其他平台与本地路径。
sys.path.insert(0, str(Path(__file__).resolve().parent))


_ADAPTERS = None


def _load_adapters() -> list:
    """加载源适配器（douyin/bilibili/youtube）。sources/ 缺失或单个模块损坏时
    静默跳过，对应平台回退通用 yt-dlp 路径（不阻塞其他平台）。"""
    global _ADAPTERS
    if _ADAPTERS is None:
        import importlib
        adapters = []
        for name in ("douyin", "bilibili", "youtube"):
            try:
                adapters.append(importlib.import_module(f"sources.{name}"))
            except Exception:
                pass  # 模块缺失或损坏都跳过该平台，回退通用 yt-dlp 路径
        _ADAPTERS = adapters
    return _ADAPTERS


def _find_adapter(url: str):
    for a in _load_adapters():
        try:
            if a.matches(url):
                return a
        except Exception:
            continue
    return None


def _get_douyin_adapter():
    """独立下载器形态（probe/download、无字幕路径）的适配器，当前即抖音。"""
    for a in _load_adapters():
        if hasattr(a, "probe") and not getattr(a, "has_subtitles", True):
            return a
    return None

# Windows 控制台默认 GBK，脚本含 emoji 输出，强制 UTF-8 避免 UnicodeEncodeError
if sys.platform == "win32":
    for _s in (sys.stdout, sys.stderr):
        if _s and hasattr(_s, "reconfigure"):
            try:
                _s.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def _seconds_to_ms(seconds: float) -> int:
    return max(0, int(round(float(seconds) * 1000)))


# ── 站点代理映射 ──────────────────────────────────────────────

SITE_PROXY_MAP: dict[str, str] = {}

_env_proxy = os.environ.get("VIDEO_SUMMARY_PROXY_MAP", "") or os.environ.get("VIDEO_TO_NOTES_PROXY_MAP", "")
if _env_proxy:
    for entry in _env_proxy.split(";"):
        if ":" in entry:
            _domain, _proxy = entry.split(":", 1)
            SITE_PROXY_MAP[_domain.strip()] = f"http://{_proxy.strip()}"


# ── 工具函数 ──────────────────────────────────────────────────


def _get_proxy_for_url(url: str, user_proxy: str | None = None) -> str | None:
    if user_proxy is not None:
        return user_proxy
    for domain, proxy in SITE_PROXY_MAP.items():
        if domain in url:
            return proxy
    return None


def _slugify(text: str) -> str:
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', text)
    text = re.sub(r'_+', '_', text).strip('_')
    return text[:80] or "video"


def _short_hash(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()[:12]


def _format_seconds(s: float) -> str:
    if s is None or s < 0:
        return "??:??"
    m, sec = divmod(int(s), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


def _format_bytes(n: float) -> str:
    if n is None or n <= 0:
        return "??"
    for unit in ["B", "KiB", "MiB", "GiB"]:
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TiB"


def run_cmd(cmd: list[str], check: bool = True, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=check, timeout=timeout)


def _is_url(text: str) -> bool:
    return text.startswith("http://") or text.startswith("https://")


def _timestamp() -> str:
    """生成时间戳，格式：YYYYMMDD_HHMMSS"""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _build_run_dir_name(title: str, user_input: str) -> str:
    """构建 run 目录名称：视频标题_时间戳"""
    slug = _slugify(title)
    ts = _timestamp()
    return f"{slug}_{ts}"


def _build_summary_filename(title: str, ts: str) -> str:
    """构建最终摘要文件名：视频标题_总结_时间戳.md"""
    slug = _slugify(title)
    return f"{slug}_总结_{ts}.md"


# ── 依赖检查 & 诊断 ─────────────────────────────────────────


def check_dependencies(fatal: bool = True, check_asr: bool = False, check_download: bool = False) -> list[tuple[str, str, bool]]:
    """检查依赖，返回 [(名称, 安装命令, 是否可用)] 列表"""
    results = []

    try:
        run_cmd(["ffmpeg", "-version"])
        results.append(("ffmpeg", "brew install ffmpeg (macOS) / apt install ffmpeg (Linux)", True))
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        results.append(("ffmpeg", "brew install ffmpeg (macOS) / apt install ffmpeg (Linux)", False))

    if check_download:
        try:
            import yt_dlp  # noqa: F401
            results.append(("yt-dlp", "pip install yt-dlp pycryptodomex", True))
        except ModuleNotFoundError:
            results.append(("yt-dlp", "pip install yt-dlp pycryptodomex", False))
        # browser_cookie3：B站 v_voucher 风控降级路径 2 依赖，可选但缺失会静默失败
        try:
            import browser_cookie3  # noqa: F401
            results.append(
                ("browser_cookie3", "pip install browser_cookie3 (可选，B站风控降级)", True)
            )
        except ModuleNotFoundError:
            results.append(
                ("browser_cookie3", "pip install browser_cookie3 (可选，B站风控降级)", False)
            )

    if check_asr:
        asr_notes = []
        asr_ok = False
        try:
            import mlx_whisper  # noqa: F401
            asr_ok = True
            asr_notes.append("mlx-whisper 可用")
        except (ModuleNotFoundError, RuntimeError) as e:
            asr_notes.append(f"mlx-whisper 不可用（{type(e).__name__}）")
        try:
            import faster_whisper  # noqa: F401
            asr_ok = True
            asr_notes.append("faster-whisper 可用")
        except (ModuleNotFoundError, RuntimeError) as e:
            asr_notes.append(f"faster-whisper 不可用（{type(e).__name__}）")
        results.append(("ASR后端(mlx-whisper/faster-whisper)", "pip install mlx-whisper / faster-whisper（任一可用即可）", asr_ok))
        results.append(("  " + "；".join(asr_notes), "—", asr_ok))

    try:
        from curl_cffi import requests as _  # noqa: F401
        results.append(("curl_cffi", "pip install curl_cffi (可选)", True))
    except ModuleNotFoundError:
        results.append(("curl_cffi", "pip install curl_cffi (可选，用于B站)", False))

    if fatal:
        missing = [(n, c) for n, c, ok in results if not ok and n in ["ffmpeg", "yt-dlp"]]
        if missing:
            print("❌ 缺少必需依赖：\n")
            for name, cmd in missing:
                print(f"  {name}: {cmd}")
            sys.exit(1)

    return results


def cmd_doctor() -> None:
    """诊断依赖和配置状态"""
    print("🔍 video-summary 诊断\n")
    results = check_dependencies(fatal=False, check_asr=True, check_download=True)
    for name, cmd, ok in results:
        status = "✅" if ok else "❌"
        print(f"  {status} {name}")
        if not ok:
            print(f"     安装：{cmd}")


# ── 源适配器派发（兼容入口，旧公开 API 签名不变） ──────────


def fetch_video_info(url: str, proxy: str | None = None) -> dict:
    """获取视频信息（标题、字幕列表）：B站有专属实现，其余走通用 yt-dlp。"""
    adapter = _find_adapter(url)
    if adapter is not None and hasattr(adapter, "fetch_info"):
        return adapter.fetch_info(url, proxy)
    from sources import yt_dlp_source
    return yt_dlp_source.fetch_info(url, proxy)


def fetch_subtitles(url: str, run_dir: Path, language: str = "zh", info: dict | None = None,
                    proxy: str | None = None) -> tuple[bool, str | None, str | None]:
    """获取平台字幕，返回 (成功, 字幕文本, 视频标题)。"""
    adapter = _find_adapter(url)
    if adapter is not None and hasattr(adapter, "fetch_subtitles"):
        return adapter.fetch_subtitles(url, run_dir, language, info, proxy)
    from sources import yt_dlp_source
    return yt_dlp_source.fetch_subtitles(url, run_dir, language, info, proxy)


def download_video(url: str, run_dir: Path, title: str | None = None, proxy: str | None = None,
                    cookies_from_browser: str | None = None) -> Path:
    """下载视频到 run 目录（按 URL 派发：B站策略链 / 通用 yt-dlp）。

    cookies_from_browser: 浏览器 cookies 来源（默认 None 不注入）；仅对 B站 注入以过风控
    """
    adapter = _find_adapter(url)
    if adapter is not None and hasattr(adapter, "download") and getattr(adapter, "has_subtitles", True):
        return adapter.download(url, run_dir, title, proxy, cookies_from_browser)
    from sources import yt_dlp_source
    return yt_dlp_source.download(url, run_dir, title, proxy, cookies_from_browser)


# 兼容旧测试/外部调用：直接暴露 B站内部实现与字幕解析（真身在 sources/ 下；
# video-to-slides 等跨技能调用方以 vs_process._parse_subtitle_file 引用，勿删）
try:
    from sources.bilibili import (  # noqa: F401
        _bilibili_detect_v_voucher,
        _bilibili_get_stream_urls_with_cookies,
        _load_browser_cookies,
        _bilibili_get_stream_urls_with_browser_cookies,
        _bilibili_get_stream_urls,
        _bilibili_extract_ids,
        _download_stream,
        _bilibili_download,
    )
    from sources.yt_dlp_source import _parse_subtitle_file  # noqa: F401
except ImportError:
    pass


# ── 音频提取 ────────────────────────────────────────────────


def extract_audio(video_path: Path, run_dir: Path) -> Path:
    """从视频提取音频"""
    audio_path = run_dir / "audio.wav"
    if audio_path.exists():
        print(f"  ✅ 音频已存在：{audio_path.name}")
        return audio_path

    print(f"  🎵 提取音频...")
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vn", "-acodec", "pcm_s16le",
        "-ar", "16000", "-ac", "1",
        str(audio_path)
    ]
    run_cmd(cmd, timeout=300)
    print(f"  ✅ 音频提取完成：{audio_path.name}")
    return audio_path


# ── ASR 转录 ────────────────────────────────────────────────


def _resolve_whisper_model(model: str, backend: str) -> str:
    """将 mlx-whisper 模型名映射为 faster-whisper 可用的模型名。

    例如 `mlx-community/whisper-large-v3-turbo` → `large-v3-turbo`；
    openai 原生模型名（`large-v3` 等）原样返回。
    """
    if backend != "faster-whisper":
        return model
    if "/" in model:
        model = model.rsplit("/", 1)[-1]
    return model[len("whisper-"):] if model.startswith("whisper-") else model


def transcribe_audio(audio_path: Path, run_dir: Path, model: str, language: str = "zh", backend: str = "auto") -> None:
    """转录音频：优先 mlx-whisper（Apple Silicon），其他平台自动 fallback 到 faster-whisper"""
    transcript_json_path = run_dir / "transcript.json"
    transcript_txt_path = run_dir / "transcript.txt"

    if transcript_json_path.exists() and transcript_txt_path.exists():
        print(f"  ✅ 转录已存在，跳过")
        return

    print(f"  🎙️  ASR 转录...")

    # 后端探测：auto = 有 mlx 用 mlx，否则 faster-whisper
    use_backend = backend
    if use_backend == "auto":
        try:
            import mlx_whisper  # noqa: F401
            use_backend = "mlx-whisper"
        except (ModuleNotFoundError, RuntimeError):
            use_backend = "faster-whisper"

    if use_backend == "mlx-whisper":
        import mlx_whisper
        result = mlx_whisper.transcribe(str(audio_path), path_or_hf_repo=model, language=language)
        segments = [
            {"start": seg.get("start"), "end": seg.get("end"), "text": str(seg.get("text", "")).strip()}
            for seg in result.get("segments", [])
        ]
        backend_name = "mlx-whisper"
    else:
        from faster_whisper import WhisperModel
        fw_model = _resolve_whisper_model(model, "faster-whisper")
        print(f"  🎙️  faster-whisper 模型：{fw_model}")
        wmodel = WhisperModel(fw_model, device="auto", compute_type="auto")
        seg_iter, _info = wmodel.transcribe(str(audio_path), language=language)
        segments = [
            {"start": seg.start, "end": seg.end, "text": seg.text.strip()}
            for seg in seg_iter
        ]
        backend_name = "faster-whisper"

    # 统一为 dict+毫秒 schema，与字幕路径保持一致（避免跨 skill 格式分歧）
    normalized = [
        {
            "start_ms": _seconds_to_ms(seg.get("start", 0)),
            "end_ms": _seconds_to_ms(seg.get("end", 0)),
            "text": seg.get("text", ""),
        }
        for seg in segments
    ]
    transcript_data = {
        "segments": normalized,
        "language": language,
        "backend": backend_name,
    }
    transcript_json_path.write_text(json.dumps(transcript_data, ensure_ascii=False, indent=2), encoding="utf-8")

    full_text = "\n".join(seg["text"] for seg in segments)
    transcript_txt_path.write_text(full_text, encoding="utf-8")

    print(f"  ✅ ASR 完成：{len(segments)} 段")


# ── 字幕保存为 transcript ─────────────────────────────────


def save_subtitle_as_transcript(subtitle_text: str, transcript_json_path: Path, transcript_txt_path: Path, language: str, run_dir: Path | None = None) -> None:
    """将字幕文本保存为 transcript 格式（带 segments key 的 dict）。"""
    lines = [line.strip() for line in subtitle_text.splitlines() if line.strip()]

    segments = []
    if run_dir:
        seg_cache = run_dir / "_subtitle_segments.json"
        if seg_cache.exists():
            try:
                segments = json.loads(seg_cache.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass

    if not segments:
        segments = [{"start_ms": 0, "end_ms": 0, "text": line} for line in lines]

    # 统一为 start_ms/end_ms 字段名
    normalized = []
    for seg in segments:
        if "start_ms" in seg:
            start_ms = int(seg["start_ms"])
            end_ms = int(seg["end_ms"])
        else:
            start_ms = _seconds_to_ms(seg.get("start", 0))
            end_ms = _seconds_to_ms(seg.get("end", 0))
        normalized.append({
            "start_ms": start_ms,
            "end_ms": end_ms,
            "text": seg.get("text", ""),
        })

    transcript_data = {"segments": normalized, "language": language, "backend": "subtitle"}
    transcript_json_path.write_text(json.dumps(transcript_data, ensure_ascii=False, indent=2), encoding="utf-8")
    transcript_txt_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"  ✅ 字幕转录完成：{len(lines)} 行")


# ── 清理 ────────────────────────────────────────────────────


def cleanup(run_dir: Path, mode: str) -> None:
    """清理中间文件"""
    if mode == "all":
        for f in run_dir.glob("audio.wav"):
            f.unlink(missing_ok=True)
            print(f"  🗑️  已删除：{f.name}")
    elif mode == "transcript-only":
        for f in run_dir.glob("*.mp4"):
            f.unlink(missing_ok=True)
            print(f"  🗑️  已删除：{f.name}")
        for f in run_dir.glob("audio.wav"):
            f.unlink(missing_ok=True)
            print(f"  🗑️  已删除：{f.name}")


# ── 主流程 ────────────────────────────────────────────────────


def _print_merge_hint(transcript_json_path: Path) -> None:
    """ASR 完成后提示 Agent 后续步骤。"""
    print(
        f"\n✅  ASR 完成：{transcript_json_path}\n"
        f"    下一步可选：\n"
        f"    - 文字摘要：读 transcript.txt 写总结（SKILL.md 步骤 6）\n"
        f"    - 图文讲义：运行 video-to-slides（阶段 0 自动合并碎段 + review）"
    )


def _finish_run(run_dir: Path, title: str, ts: str,
                transcript_json_path: Path, transcript_txt_path: Path,
                args: argparse.Namespace, source_label: str) -> None:
    """共用收尾：占位摘要 + 清理 + 输出结果 JSON。"""
    # 生成最终摘要文件：视频标题_总结_时间戳.md
    summary_path = run_dir / _build_summary_filename(title, ts)
    if not summary_path.exists():
        # 脚本只创建占位文件，摘要正文由 Agent 按 SKILL.md 步骤 6 补写
        summary_path.write_text(
            f"# {title}\n\n"
            f"> 本文件由脚本自动创建的占位文件，摘要正文需按 SKILL.md 步骤 6 由 Agent 读取 transcript.txt 后补写。\n",
            encoding="utf-8",
        )
        print(f"  📝 创建占位摘要：{summary_path.name}（待 Agent 补写）")

    # 清理
    if args.cleanup:
        cleanup(run_dir, args.cleanup)

    # 输出结果
    result = {
        "run_dir": str(run_dir.resolve()),
        "title": title,
        "source": source_label,
        "transcript_json": str(transcript_json_path.resolve()) if transcript_json_path.exists() else None,
        "transcript_txt": str(transcript_txt_path.resolve()) if transcript_txt_path.exists() else None,
        "summary_md": str(summary_path.resolve()) if summary_path.exists() else None,
    }
    source_desc = {"subtitle": "字幕", "asr": "ASR", "douyin": "ASR"}.get(source_label, source_label)
    print(f"\n✅ 完成！（来源：{source_desc}）")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_process(args: argparse.Namespace) -> None:
    """主流程：URL/本地路径 → 字幕优先 → ASR fallback → 输出"""
    user_input = args.input
    douyin_source = _get_douyin_adapter()
    if douyin_source is not None:
        # 支持包裹文本（如"看这个 https://v.douyin.com/xxx"）：提取规整 URL；本地路径原样返回
        user_input = douyin_source.normalize_url(user_input)
    is_url = _is_url(user_input)
    if is_url:
        # 站点代理映射（VIDEO_SUMMARY_PROXY_MAP）：按域名自动选代理，命令行 --proxy 优先
        args.proxy = _get_proxy_for_url(user_input, args.proxy)

    if douyin_source is None and "douyin.com" in user_input:
        print("❌ 缺少抖音适配器或 playwright：pip install playwright && python -m playwright install chromium",
              file=sys.stderr)
        raise SystemExit(2)

    check_dependencies(
        fatal=True,
        check_asr=not is_url or args.no_subtitle,
        check_download=is_url,
    )

    base_dir = Path(args.output_dir)
    base_dir.mkdir(parents=True, exist_ok=True)

    # 抖音：web API 需实时签名（yt-dlp 已被风控 403），走专用源适配器，无字幕路径直接 ASR
    if is_url and douyin_source is not None and douyin_source.matches(user_input):
        print(f"🔗 {user_input}")
        try:
            meta = douyin_source.probe(user_input, headless=not getattr(args, "douyin_headful", False))
        except ImportError as e:
            print("❌ 缺少 playwright 依赖：pip install playwright && python -m playwright install chromium",
                  file=sys.stderr)
            raise SystemExit(2) from e
        except (ValueError, RuntimeError) as e:
            print(f"❌ 抖音解析失败：{e}", file=sys.stderr)
            raise SystemExit(2) from e
        title = meta.title
        print(f"📝 视频标题：{title}")
        run_dir = base_dir / _build_run_dir_name(title, user_input)
        run_dir.mkdir(parents=True, exist_ok=True)
        ts = _timestamp()
        transcript_json_path = run_dir / "transcript.json"
        transcript_txt_path = run_dir / "transcript.txt"
        try:
            video_path = douyin_source.download(meta, run_dir).video_path
        except (ValueError, RuntimeError) as e:
            print(f"❌ 抖音下载失败：{e}", file=sys.stderr)
            raise SystemExit(2) from e
        audio_path = extract_audio(video_path, run_dir)
        transcribe_audio(audio_path, run_dir, args.asr_model, args.language, args.asr_backend)
        _print_merge_hint(transcript_json_path)
        return _finish_run(run_dir, title, ts, transcript_json_path, transcript_txt_path,
                           args, source_label="douyin")

    # 先获取标题（URL输入时）
    title = None
    video_info = None
    if is_url:
        try:
            video_info = fetch_video_info(user_input, proxy=args.proxy)
            title = video_info.get("title")
        except Exception:
            pass

    if not title:
        title = Path(user_input).stem if not is_url else "video"

    # 构建 run 目录名称：视频标题_时间戳
    run_dir_name = _build_run_dir_name(title, user_input)
    run_dir = base_dir / run_dir_name
    run_dir.mkdir(parents=True, exist_ok=True)

    # 记录时间戳用于后续文件名
    ts = _timestamp()
    transcript_json_path = run_dir / "transcript.json"
    transcript_txt_path = run_dir / "transcript.txt"

    if is_url:
        print(f"🔗 {user_input}")
        print(f"📝 视频标题：{title}")

        print("\n🔤 尝试获取平台字幕...")
        has_subtitle, subtitle_text, fetched_title = fetch_subtitles(user_input, run_dir, args.language, info=video_info, proxy=args.proxy)

        if fetched_title:
            title = fetched_title

        if has_subtitle and subtitle_text:
            save_subtitle_as_transcript(subtitle_text, transcript_json_path, transcript_txt_path, args.language, run_dir)
        else:
            title = title or "video"
            video_path = download_video(user_input, run_dir, title, args.proxy,
                                        cookies_from_browser=getattr(args, 'cookies_from_browser', None))
            audio_path = extract_audio(video_path, run_dir)
            transcribe_audio(audio_path, run_dir, args.asr_model, args.language, args.asr_backend)
            _print_merge_hint(transcript_json_path)

    else:
        video_path = Path(user_input).expanduser().resolve()
        if not video_path.exists():
            print(f"❌ 视频文件不存在：{video_path}", file=sys.stderr)
            sys.exit(2)

        print(f"📁 {video_path.name}")
        print(f"📝 视频标题：{title}")

        run_video = run_dir / video_path.name
        if not run_video.exists():
            try:
                os.symlink(str(video_path), str(run_video))
                print(f"  🔗 已链接视频：{run_video.name}")
            except OSError:
                import shutil
                shutil.copy2(str(video_path), str(run_video))
                print(f"  📋 已复制视频：{run_video.name}")

        audio_path = extract_audio(run_video, run_dir)
        transcribe_audio(audio_path, run_dir, args.asr_model, args.language, args.asr_backend)
        _print_merge_hint(transcript_json_path)

    # 生成占位摘要 / 清理 / 输出结果
    _finish_run(run_dir, title, ts, transcript_json_path, transcript_txt_path,
                args, source_label="subtitle" if is_url and has_subtitle else "asr")


def _build_arg_parser():
    parser = argparse.ArgumentParser(
        description="video-summary：视频 URL 或本地文件 → 下载 + 字幕/ASR → 摘要"
    )
    parser.add_argument("input", nargs="?", help="视频 URL 或本地文件路径；也可传 doctor 诊断")
    parser.add_argument("--output-dir", default="./runs", help="产物目录（默认 ./runs）")
    parser.add_argument("--asr-model", default="mlx-community/whisper-large-v3-turbo",
                        help="ASR 模型（mlx-whisper 用 mlx-community/* 或 openai 模型名；faster-whisper 自动映射）")
    parser.add_argument("--asr-backend", default="auto", choices=["auto", "mlx-whisper", "faster-whisper"],
                        help="ASR 后端：auto 自动探测（默认）；mlx-whisper 仅 Apple Silicon；faster-whisper 通用（Windows/Linux）")
    parser.add_argument("--language", default="zh", help="语言（默认 zh）")
    parser.add_argument("--proxy", default=None, help="代理地址")
    parser.add_argument("--cleanup", default=None, choices=["all", "transcript-only"], help="清理模式")
    parser.add_argument("--no-subtitle", action="store_true", help="跳过字幕，强制使用 ASR")
    parser.add_argument("--cookies-from-browser", default=None,
                        choices=["chrome", "firefox", "safari", "edge"],
                        help="浏览器 cookies 来源（B 站风控需登录态时显式传入；不传则所有平台不注入）")
    parser.add_argument("--douyin-headful", action="store_true",
                        help="抖音下载强制有头浏览器（默认无头优先，失败自动转有头）")
    return parser


def main():
    parser = _build_arg_parser()
    args = parser.parse_args()

    if args.input == "doctor":
        cmd_doctor()
        return

    if not args.input:
        parser.print_help()
        sys.exit(1)

    cmd_process(args)


if __name__ == "__main__":
    main()
