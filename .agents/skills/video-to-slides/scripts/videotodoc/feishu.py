# 已废弃：飞书发布功能已迁移到 skills/feishu-markdown-publish/。
# 本模块仅保留以避免旧代码 import 报错，新代码请不要使用。

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path

from .config import Settings
from .models import Section
from .utils import VideoToDocError, run_command


def publish_to_feishu(markdown_path: Path, title: str, sections: list[Section], settings: Settings, dry_run: bool = False) -> str:
    args = [
        "lark-cli",
        "docs",
        "+create",
        "--title",
        title,
        "--markdown",
        f"@{markdown_path}",
        "--as",
        settings.feishu_identity,
    ]
    if settings.feishu_folder_token:
        args += ["--folder-token", settings.feishu_folder_token]
    if dry_run:
        commands = [" ".join(shlex.quote(item) for item in args)]
        for section in sections:
            image_path = Path(section.image_path)
            commands.append(
                " ".join(
                    shlex.quote(item)
                    for item in [
                        "lark-cli",
                        "docs",
                        "+media-insert",
                        "--doc",
                        "<created-doc>",
                        "--file",
                        str(image_path),
                        "--type",
                        "image",
                        "--align",
                        "center",
                        "--caption",
                        f"第 {section.slide_index} 页",
                        "--as",
                        settings.feishu_identity,
                    ]
                )
            )
        return "\n".join(commands)

    result = run_command(args)
    doc_ref = _extract_doc_ref(result.stdout)
    if not doc_ref:
        raise VideoToDocError(f"飞书文档创建成功但无法解析文档 ID/URL：\n{result.stdout}")

    # Markdown 内的本地图片未必会自动上传，所以逐张显式插入一次，保证飞书文档有真实媒体块。
    for section in sections:
        image_path = Path(section.image_path)
        if not image_path.exists():
            continue
        media_args = [
            "lark-cli",
            "docs",
            "+media-insert",
            "--doc",
            doc_ref,
            "--file",
            str(image_path),
            "--type",
            "image",
            "--align",
            "center",
            "--caption",
            f"第 {section.slide_index} 页",
            "--as",
            settings.feishu_identity,
        ]
        run_command(media_args)
    return doc_ref


def _extract_doc_ref(output: str) -> str | None:
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict):
        for key in ("url", "document_url", "doc_url", "token", "document_id", "doc_id"):
            value = _find_key(data, key)
            if isinstance(value, str) and value:
                return value
    match = re.search(r"https://\S+", output)
    if match:
        return match.group(0)
    return None


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
