from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path


class VideoToDocError(RuntimeError):
    pass


def run_command(
    args: list[str],
    cwd: Path | None = None,
    *,
    timeout: float = 120,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise VideoToDocError(f"找不到命令：{args[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        cmd_str = " ".join(args)
        details = ""
        if exc.stderr:
            stderr_text = exc.stderr if isinstance(exc.stderr, str) else exc.stderr.decode("utf-8", errors="replace")
            if stderr_text.strip():
                details = f"\nstderr: {stderr_text.strip()}"
        elif exc.stdout:
            stdout_text = exc.stdout if isinstance(exc.stdout, str) else exc.stdout.decode("utf-8", errors="replace")
            if stdout_text.strip():
                details = f"\nstdout: {stdout_text.strip()}"
        raise VideoToDocError(f"命令执行超时（{timeout}s）：{cmd_str}{details}") from exc
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or exc.stdout.strip()
        raise VideoToDocError(f"命令执行失败：{' '.join(args)}\n{message}") from exc


def file_md5(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def slugify(value: str, max_len: int = 80) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", value, flags=re.UNICODE).strip("_")
    return cleaned[:max_len] or "video"


def ensure_file(path: Path, label: str) -> None:
    if not path.exists() or not path.is_file():
        raise VideoToDocError(f"{label}不存在：{path}")


def seconds_to_ms(seconds: float) -> int:
    return max(0, int(round(seconds * 1000)))


def ms_to_seconds(ms: int) -> float:
    return ms / 1000.0
