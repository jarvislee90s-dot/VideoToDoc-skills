from __future__ import annotations


def inject_tidy_tree_config(mmd_text: str) -> str:
    """在 Mermaid mindmap 文本前注入 tidy-tree 布局配置。"""
    frontmatter = "---\nconfig:\n  layout: tidy-tree\n---\n\n"
    return frontmatter + mmd_text.lstrip()


def add_chapter_numbers(mmd_text: str) -> str:
    """为 Mermaid mindmap 中的 1 级章节节点添加序号。"""
    lines = mmd_text.splitlines()
    chapter_index = 0
    result: list[str] = []
    for line in lines:
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if indent == 4 and stripped and not stripped.startswith("root"):
            chapter_index += 1
            line = f"{line[:indent]}{chapter_index}. {stripped}"
        result.append(line)
    return "\n".join(result) + "\n"


def count_nodes(mmd_text: str) -> int:
    """统计 mindmap 中的节点数量（包含根节点）。"""
    count = 0
    for line in mmd_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped in {"mindmap", "---"} or stripped.startswith("config:") or stripped.startswith("layout:"):
            continue
        count += 1
    return count


def split_mmd_by_chapters(
    mmd_text: str,
    max_nodes: int = 80,
    min_chapters: int = 2,
    min_nodes: int = 10,
) -> list[str]:
    """按 1 级章节将 mindmap 拆分为多个子图，避免单图过大或子图过稀疏。"""
    lines = mmd_text.splitlines()
    root_lines: list[str] = []
    chapters: list[list[str]] = []
    current_chapter: list[str] | None = None

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped == "mindmap":
            continue
        if stripped.startswith("root"):
            root_lines.append(line)
            continue
        indent = len(line) - len(line.lstrip())
        if indent == 4:
            if current_chapter is not None:
                chapters.append(current_chapter)
            current_chapter = [line]
        elif current_chapter is not None and indent > 4:
            current_chapter.append(line)
        else:
            root_lines.append(line)
    if current_chapter:
        chapters.append(current_chapter)

    if not chapters:
        return [mmd_text]

    total_nodes = count_nodes(mmd_text)
    if total_nodes <= max_nodes and len(chapters) >= min_chapters:
        return [mmd_text]

    def chapter_node_count(ch: list[str]) -> int:
        return 1 + sum(1 for line in ch if len(line) - len(line.lstrip()) > 4)

    chunks: list[list[list[str]]] = []
    current_chunk: list[list[str]] = []
    current_nodes = 0

    for ch in chapters:
        cn = chapter_node_count(ch)
        if not current_chunk:
            current_chunk.append(ch)
            current_nodes += cn
        elif current_nodes + cn <= max_nodes and len(current_chunk) < min_chapters:
            current_chunk.append(ch)
            current_nodes += cn
        elif current_nodes < min_nodes and current_nodes + cn <= max_nodes:
            current_chunk.append(ch)
            current_nodes += cn
        else:
            chunks.append(current_chunk)
            current_chunk = [ch]
            current_nodes = cn
    if current_chunk:
        chunks.append(current_chunk)

    # 合并尾部过小的 chunk
    while len(chunks) >= 2:
        last = chunks[-1]
        second_last = chunks[-2]
        last_nodes = sum(chapter_node_count(ch) for ch in last)
        second_last_nodes = sum(chapter_node_count(ch) for ch in second_last)
        if last_nodes < min_nodes and second_last_nodes + last_nodes <= max_nodes:
            chunks[-2] = second_last + last
            chunks.pop()
        else:
            break

    result: list[str] = []
    for chunk in chunks:
        body = "\n".join(root_lines + [line for ch in chunk for line in ch])
        result.append(f"mindmap\n{body}\n")
    return result
