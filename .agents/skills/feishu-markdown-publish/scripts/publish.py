#!/usr/bin/env python3
"""把一个本地 Markdown 按图文顺序发布到飞书文档。"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from _project import find_project_dir


@dataclass
class Section:
    title: str
    body: str
    image: Path | None
    caption: str


@dataclass
class ParsedDoc:
    title: str
    header: str
    sections: list[Section]
    mindmap: Section | None


def main() -> int:
    parser = argparse.ArgumentParser(description="把一个本地 Markdown 按图文顺序发布到飞书文档。")
    parser.add_argument("markdown", type=Path, help="本地 Markdown 文件路径")
    parser.add_argument("target", nargs="?", default=None,
                        help="可选：飞书 wiki space URL/ID；不传则发布到公共文档")
    parser.add_argument("--title", default=None, help="文档标题（默认从 Markdown H1 提取）")
    parser.add_argument("--project-dir", type=Path, default=None)
    parser.add_argument("--identity", choices=["user", "bot"], default="user")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    markdown_path = args.markdown.expanduser().resolve()
    if not markdown_path.exists():
        print(f"Markdown 不存在：{markdown_path}", file=sys.stderr)
        return 2

    project_dir = find_project_dir(args.project_dir, markdown_path)
    parsed = parse_markdown(markdown_path)
    title = args.title or parsed.title
    publish_dir = project_dir / "runs" / "_feishu_publish" / safe_name(markdown_path.stem)
    publish_dir.mkdir(parents=True, exist_ok=True)

    publisher = Publisher(project_dir, publish_dir, args.identity, args.dry_run)
    wiki_space = parse_wiki_space(args.target)

    # 断点续传：检测已有进度
    progress = publisher.load_progress()
    if progress:
        doc_ref = progress["doc_ref"]
        start_index = progress["last_section"] + 1
        print(f"  ♻️  检测到断点续传，从第 {start_index} 页继续：{doc_ref}")
    else:
        doc_ref = publisher.create_doc(
            title, write_chunk(publish_dir, "initial", f"# {title}\n\n"), wiki_space,
        )
        publisher.update_doc(
            doc_ref, write_chunk(publish_dir, "header", f"# {title}\n\n{parsed.header}"), "overwrite",
        )
        start_index = 1

    total = len(parsed.sections)
    for index, section in enumerate(parsed.sections, start=1):
        if index < start_index:
            continue
        body_parts = []
        if section.body:
            body_parts.append(ensure_blank(section.body))
        if index < total:
            body_parts.append("\n\n---\n\n")
        body_text = "\n\n".join(body_parts)

        if section.image:
            publisher.append_doc(doc_ref, write_chunk(publish_dir, f"section_{index:03d}_title", ensure_blank(section.title)))
            publisher.insert_image(doc_ref, section.image, section.caption)
            if body_text:
                publisher.append_doc(doc_ref, write_chunk(publish_dir, f"section_{index:03d}_body", body_text))
        else:
            combined = ensure_blank(section.title) + body_text
            if combined.strip():
                publisher.append_doc(doc_ref, write_chunk(publish_dir, f"section_{index:03d}_content", combined))
        publisher.save_progress(doc_ref, index)
        print(f"  📤 第 {index}/{total} 页已发布", flush=True)

    if parsed.mindmap:
        if parsed.mindmap.image:
            publisher.append_doc(doc_ref, write_chunk(publish_dir, "mindmap_title", ensure_blank(parsed.mindmap.title)))
            publisher.insert_image(doc_ref, parsed.mindmap.image, parsed.mindmap.caption)
            if parsed.mindmap.body:
                publisher.append_doc(doc_ref, write_chunk(publish_dir, "mindmap_body", ensure_blank(parsed.mindmap.body)))
        else:
            mindmap_combined = ensure_blank(parsed.mindmap.title) + ensure_blank(parsed.mindmap.body)
            if mindmap_combined.strip():
                publisher.append_doc(doc_ref, write_chunk(publish_dir, "mindmap_content", mindmap_combined))

    publisher.clear_progress()

    print("飞书文档发布 dry-run：" if args.dry_run else "飞书文档发布完成：")
    print(doc_ref)
    return 0


class Publisher:
    def __init__(self, project_dir: Path, publish_dir: Path, identity: str, dry_run: bool) -> None:
        self.project_dir = project_dir
        self.publish_dir = publish_dir
        self.identity = identity
        self.dry_run = dry_run
        self.asset_dir = publish_dir / "assets"
        self.asset_dir.mkdir(parents=True, exist_ok=True)
        self.progress_path = publish_dir / "publish_progress.json"

    def create_doc(self, title: str, markdown_path: Path, wiki_space: str | None) -> str:
        cmd = [
            "lark-cli", "docs", "+create",
            "--api-version", "v2",
            "--doc-format", "markdown",
            "--content", f"@{self._cli_path(markdown_path)}",
            "--as", self.identity,
        ]
        if wiki_space:
            cmd += ["--parent-token", wiki_space]
        if self.dry_run:
            print("DRY-RUN", " ".join(cmd))
            return f"dry-run:{title}"
        result = self._run(cmd)
        doc_ref = _extract_doc_ref(result.stdout)
        if not doc_ref:
            raise RuntimeError(f"无法从 lark-cli 输出解析文档地址：\n{result.stdout}")
        return doc_ref

    def update_doc(self, doc_ref: str, markdown_path: Path, mode: str) -> None:
        cmd = [
            "lark-cli", "docs", "+update",
            "--api-version", "v2",
            "--doc", doc_ref, "--command", mode,
            "--doc-format", "markdown",
            "--content", f"@{self._cli_path(markdown_path)}",
            "--as", self.identity,
        ]
        if self.dry_run:
            print("DRY-RUN", " ".join(cmd))
            return
        self._run(cmd)

    def append_doc(self, doc_ref: str, markdown_path: Path) -> None:
        self.update_doc(doc_ref, markdown_path, "append")

    def insert_image(self, doc_ref: str, image_path: Path, caption: str) -> None:
        if not image_path.exists():
            print(f"图片不存在，已跳过：{image_path}", file=sys.stderr)
            return
        staged = self._stage_image(image_path)
        cmd = [
            "lark-cli", "docs", "+media-insert",
            "--doc", doc_ref, "--file", self._cli_path(staged),
            "--type", "image", "--align", "center", "--caption", caption,
            "--as", self.identity,
        ]
        if self.dry_run:
            print("DRY-RUN", " ".join(cmd))
            return
        self._run(cmd)

    def _stage_image(self, image_path: Path) -> Path:
        target = self.asset_dir / f"{safe_name(image_path.stem)}{image_path.suffix.lower()}"
        if target.resolve() != image_path.resolve():
            shutil.copy2(image_path, target)
        return target

    def _run(self, args: list[str], retries: int = 4, timeout: float = 60) -> subprocess.CompletedProcess[str]:
        last_err = ""
        for attempt in range(retries):
            try:
                result = subprocess.run(
                    args, cwd=self.project_dir, text=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired as exc:
                last_err = f"lark-cli 调用超时（{timeout}s）：{' '.join(args)}"
                if attempt < retries - 1:
                    wait = 5 * (attempt + 1)
                    print(f"  ⚠️ 第 {attempt+1} 次超时，{wait}s 后重试", file=sys.stderr)
                    time.sleep(wait)
                    continue
                raise RuntimeError(last_err)
            if result.returncode == 0:
                return result
            last_err = result.stderr.strip() or result.stdout.strip()
            retryable = any(k in last_err for k in ("1771001", "server internal error", "rate limit", "9999", "too many", "timeout"))
            if attempt < retries - 1 and retryable:
                wait = 5 * (attempt + 1)
                print(f"  ⚠️ 第 {attempt+1} 次失败，{wait}s 后重试：{last_err[:120]}", file=sys.stderr)
                time.sleep(wait)
                continue
            raise RuntimeError(last_err)
        raise RuntimeError(last_err)

    def _cli_path(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self.project_dir))
        except ValueError:
            # 路径不在项目根下时回退到绝对路径
            return str(path.resolve())

    def load_progress(self) -> dict | None:
        if not self.progress_path.exists():
            return None
        return json.loads(self.progress_path.read_text(encoding="utf-8"))

    def save_progress(self, doc_ref: str, last_section: int) -> None:
        # dry-run 不写断点状态，避免假 doc_ref 污染真实断点续传
        if self.dry_run:
            return
        self.progress_path.write_text(
            json.dumps({"doc_ref": doc_ref, "last_section": last_section}, ensure_ascii=False),
            encoding="utf-8",
        )

    def clear_progress(self) -> None:
        # dry-run 不删断点状态，保留真实发布留下的续传进度
        if self.dry_run:
            return
        self.progress_path.unlink(missing_ok=True)


# ── Markdown 解析 ──────────────────────────────────────────


def parse_markdown(markdown_path: Path) -> ParsedDoc:
    lines = markdown_path.read_text(encoding="utf-8").splitlines()
    title = markdown_path.stem
    header_lines: list[str] = []
    sections: list[Section] = []
    mindmap: Section | None = None
    current_title: str | None = None
    current_lines: list[str] = []
    current_is_mindmap = False

    def flush() -> None:
        nonlocal current_title, current_lines, current_is_mindmap, mindmap
        if current_title is None:
            return
        section = _build_section(current_title, current_lines, markdown_path.parent)
        if current_is_mindmap:
            mindmap = section
        else:
            sections.append(section)
        current_title = None
        current_lines = []
        current_is_mindmap = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# ") and current_title is None and not header_lines:
            title = stripped[2:].strip() or title
            continue
        if stripped.startswith("### "):
            flush()
            current_title = stripped
            current_lines = []
            current_is_mindmap = False
            continue
        if stripped.startswith("## 思维导图"):
            flush()
            current_title = stripped
            current_lines = []
            current_is_mindmap = True
            continue
        if current_title is None:
            header_lines.append(line)
        else:
            current_lines.append(line)
    flush()

    header = _cleanup_lines(header_lines)
    return ParsedDoc(title=title, header=header, sections=sections, mindmap=mindmap)


def _build_section(title: str, lines: list[str], base_dir: Path) -> Section:
    body_lines: list[str] = []
    image: Path | None = None
    caption = ""
    for line in lines:
        stripped = line.strip()
        match = re.fullmatch(r"!\[([^\]]*)\]\(([^)]+)\)", stripped)
        if match and image is None:
            image = _resolve_image_path(match.group(2).strip(), base_dir)
            caption = match.group(1).strip() or image.stem
            continue
        if stripped == "---":
            continue
        body_lines.append(line)
    return Section(title=title, body=_cleanup_lines(body_lines), image=image, caption=caption)


def _resolve_image_path(raw: str, base_dir: Path) -> Path:
    path = Path(raw.strip("<>"))
    return path if path.is_absolute() else (base_dir / path).resolve()


def _cleanup_lines(lines: list[str]) -> str:
    text = "\n".join(lines).strip()
    if not text:
        return ""
    return re.sub(r"\n{3,}", "\n\n", text).rstrip() + "\n\n"


def ensure_blank(text: str) -> str:
    return text.strip() + "\n\n" if text.strip() else ""


def write_chunk(publish_dir: Path, name: str, content: str) -> Path:
    path = publish_dir / f"{safe_name(name)}.md"
    path.write_text(content, encoding="utf-8")
    return path


# ── 工具函数 ──────────────────────────────────────────────


def parse_wiki_space(target: str | None) -> str | None:
    if not target:
        return None
    target = target.strip()
    parsed = urlparse(target)
    if parsed.scheme and parsed.netloc:
        match = re.search(r"/wiki/space/([^/?#]+)", parsed.path)
        return match.group(1) if match else None
    return target


def _extract_doc_ref(output: str) -> str | None:
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict):
        for key in ("url", "document_url", "doc_url", "token", "document_id", "doc_id"):
            found = _find_key(data, key)
            if isinstance(found, str) and found:
                return found
    match = re.search(r"https://\S+", output)
    return match.group(0) if match else None


def _find_key(data: object, target: str) -> object:
    if isinstance(data, dict):
        if target in data:
            return data[target]
        for value in data.values():
            found = _find_key(value, target)
            if found is not None:
                return found
    if isinstance(data, list):
        for item in data:
            found = _find_key(item, target)
            if found is not None:
                return found
    return None


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^\w.-]+", "_", value, flags=re.UNICODE).strip("._")
    return cleaned or "publish"


if __name__ == "__main__":
    raise SystemExit(main())
