#!/usr/bin/env python3
"""发布当前 run 的原文版和整理版飞书文档。

需要在用户普通终端运行，以便 lark-cli 访问本机登录态。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUN = PROJECT_DIR / "runs/01_第一讲_期权实盘应该避开的_七大误区_08258178726c"
DEFAULT_TITLE = "01_第一讲 期权实盘应该避开的“七大误区”"


def main() -> int:
    args = [arg for arg in sys.argv[1:] if arg != "--repair-existing"]
    repair_mode = "--repair-existing" in sys.argv
    run_dir = Path(args[0]).resolve() if args else DEFAULT_RUN
    title = args[1] if len(args) > 1 else DEFAULT_TITLE
    if not run_dir.exists():
        print(f"run 目录不存在：{run_dir}", file=sys.stderr)
        return 2

    if repair_mode:
        return repair_existing(run_dir)

    outputs = []
    for suffix, markdown_name in (("原文版", "draft_compact.md"), ("整理版", "draft_semantic.md")):
        markdown_path = run_dir / markdown_name
        if not markdown_path.exists():
            print(f"找不到 Markdown：{markdown_path}", file=sys.stderr)
            return 2
        doc_title = f"{title} {suffix}"
        doc_ref = create_doc(doc_title, write_publish_chunk(markdown_path, "initial", f"# {doc_title}\n\n"))
        build_ordered_doc(doc_ref, markdown_path, run_dir)
        outputs.append((suffix, doc_ref))

    print("飞书文档发布完成：")
    for suffix, doc_ref in outputs:
        print(f"- {suffix}: {doc_ref}")
    return 0


def repair_existing(run_dir: Path) -> int:
    pairs = [
        (
            "原文版",
            "draft_compact.md",
            "https://www.feishu.cn/docx/NXArdZf0DowaXMx1aeYc5iRbnmh",
        ),
        (
            "整理版",
            "draft_semantic.md",
            "https://www.feishu.cn/docx/IwR8dO9RGoNHk2xTl3NcDkR6nBc",
        ),
    ]
    for suffix, markdown_name, doc_ref in pairs:
        markdown_path = run_dir / markdown_name
        update_doc(doc_ref, write_publish_chunk(markdown_path, "reset", "# 正在重建文档\n\n"), mode="overwrite")
        build_ordered_doc(doc_ref, markdown_path, run_dir)
        print(f"已修复：{suffix} {doc_ref}")
    return 0


def build_ordered_doc(doc_ref: str, markdown_path: Path, run_dir: Path) -> None:
    parsed = parse_markdown_doc(markdown_path)
    update_doc(doc_ref, write_publish_chunk(markdown_path, "header", parsed["header"]), mode="overwrite")
    for index, section in enumerate(parsed["sections"], start=1):
        append_doc(doc_ref, write_publish_chunk(markdown_path, f"section_{index}_title", section["title"]))
        if section["image"]:
            insert_image(doc_ref, section["image"], section["caption"])
        if section["body"]:
            append_doc(doc_ref, write_publish_chunk(markdown_path, f"section_{index}_body", section["body"]))
    append_doc(doc_ref, write_publish_chunk(markdown_path, "mindmap_title", "\n\n## 思维导图\n\n"))
    insert_image(doc_ref, run_dir / "mindmap.png", "思维导图")


def parse_markdown_doc(markdown_path: Path) -> dict[str, object]:
    lines = markdown_path.read_text(encoding="utf-8").splitlines()
    header_lines: list[str] = []
    sections: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    body_lines: list[str] = []

    def flush_current() -> None:
        nonlocal current, body_lines
        if not current:
            return
        current["body"] = cleanup_body(body_lines)
        sections.append(current)
        current = None
        body_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("### "):
            flush_current()
            current = {"title": stripped + "\n\n", "image": None, "caption": "", "body": ""}
            continue
        if stripped.startswith("## 思维导图"):
            flush_current()
            break
        if current is None:
            if not stripped.startswith("# "):
                header_lines.append(line)
            continue
        image_match = re.fullmatch(r"!\[([^\]]*)\]\(([^)]+)\)", stripped)
        if image_match:
            raw_path = image_match.group(2)
            current["image"] = (markdown_path.parent / raw_path).resolve()
            current["caption"] = image_match.group(1) or Path(raw_path).stem
            continue
        if stripped == "---":
            continue
        body_lines.append(line)

    flush_current()
    header = "\n".join(line for line in header_lines if line.strip()).strip()
    if header:
        header += "\n\n"
    return {"header": header, "sections": sections}


def cleanup_body(lines: list[str]) -> str:
    text = "\n".join(lines).strip()
    if not text:
        return ""
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.rstrip() + "\n\n"


def write_publish_chunk(markdown_path: Path, name: str, content: str) -> Path:
    output_dir = PROJECT_DIR / "runs" / "_feishu_publish" / markdown_path.stem
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{name}.md"
    output_path.write_text(content, encoding="utf-8")
    return output_path


def create_doc(title: str, markdown_path: Path) -> str:
    result = run(
        [
            "lark-cli",
            "docs",
            "+create",
            "--title",
            title,
            "--markdown",
            f"@{cli_path(markdown_path)}",
            "--as",
            "user",
        ]
    )
    doc_ref = extract_doc_ref(result.stdout)
    if not doc_ref:
        raise RuntimeError(f"无法从 lark-cli 输出解析文档地址：\n{result.stdout}")
    return doc_ref


def update_doc(doc_ref: str, markdown_path: Path, mode: str = "overwrite") -> None:
    run(
        [
            "lark-cli",
            "docs",
            "+update",
            "--doc",
            doc_ref,
            "--mode",
            mode,
            "--markdown",
            f"@{cli_path(markdown_path)}",
            "--as",
            "user",
        ]
    )


def append_doc(doc_ref: str, markdown_path: Path) -> None:
    update_doc(doc_ref, markdown_path, mode="append")


def insert_image(doc_ref: str, image_path: Path, caption: str) -> None:
    if not image_path.exists():
        return
    run(
        [
            "lark-cli",
            "docs",
            "+media-insert",
            "--doc",
            doc_ref,
            "--file",
            cli_path(image_path),
            "--type",
            "image",
            "--align",
            "center",
            "--caption",
            caption,
            "--as",
            "user",
        ]
    )


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=PROJECT_DIR, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result


def extract_doc_ref(output: str) -> str | None:
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict):
        for key in ("url", "document_url", "doc_url", "token", "document_id", "doc_id"):
            found = find_key(data, key)
            if isinstance(found, str) and found:
                return found
    match = re.search(r"https://\S+", output)
    return match.group(0) if match else None


def find_key(data: object, target: str) -> object:
    if isinstance(data, dict):
        if target in data:
            return data[target]
        for value in data.values():
            found = find_key(value, target)
            if found is not None:
                return found
    if isinstance(data, list):
        for item in data:
            found = find_key(item, target)
            if found is not None:
                return found
    return None


def cli_path(path: Path) -> str:
    path = path.resolve()
    try:
        return str(path.relative_to(PROJECT_DIR))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    raise SystemExit(main())
