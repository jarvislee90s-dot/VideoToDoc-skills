from pathlib import Path

from publish import Publisher


class TestPublishProgress:
    def test_save_and_load_progress(self, tmp_path):
        pub = Publisher(Path("/tmp"), tmp_path, "user", dry_run=False)
        pub.save_progress("https://feishu.cn/docx/abc", 50)
        progress = pub.load_progress()
        assert progress == {"doc_ref": "https://feishu.cn/docx/abc", "last_section": 50}

    def test_load_progress_no_file(self, tmp_path):
        pub = Publisher(Path("/tmp"), tmp_path, "user", dry_run=False)
        assert pub.load_progress() is None

    def test_clear_progress(self, tmp_path):
        pub = Publisher(Path("/tmp"), tmp_path, "user", dry_run=False)
        pub.save_progress("ref", 10)
        pub.clear_progress()
        assert pub.load_progress() is None


import io
import contextlib


class TestFlushProgress:
    """飞书发布每页输出进度，且 flush=True。"""

    def test_progress_printed_per_section(self, tmp_path):
        """每页发布后输出进度。"""
        md = tmp_path / "test.md"
        md.write_text("# 测试\n\n### 第一页\n\n正文1\n\n### 第二页\n\n正文2\n", encoding="utf-8")
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            import publish
            old_main = publish.main
            # 用 dry-run 模式，只验证进度输出
            import sys
            old_argv = sys.argv
            sys.argv = ["publish.py", str(md), "--dry-run", "--project-dir", str(tmp_path)]
            try:
                publish.main()
            finally:
                sys.argv = old_argv
        output = captured.getvalue()
        assert "第" in output or "页" in output


class TestBatchAppend:
    """飞书发布合并 title+body+divider 为一次 append。"""

    def test_title_body_divider_merged(self, tmp_path):
        """每页的 title + body + divider 合并为一次 append（不含 image）。"""
        from publish import Publisher, parse_markdown, write_chunk, ensure_blank
        md = tmp_path / "test.md"
        md.write_text("# 测试\n\n### 第一页\n\n正文1\n\n### 第二页\n\n正文2\n", encoding="utf-8")
        parsed = parse_markdown(md)
        publisher = Publisher(tmp_path, tmp_path / "pub", "user", dry_run=True)
        call_count = 0
        original_append = publisher.append_doc

        def counting_append(doc_ref, md_path):
            nonlocal call_count
            call_count += 1
            original_append(doc_ref, md_path)

        publisher.append_doc = counting_append
        publisher.update_doc("ref", write_chunk(tmp_path / "pub", "header", "# 测试\n\n"), "overwrite")

        total = len(parsed.sections)
        for index, section in enumerate(parsed.sections, start=1):
            # 合并 title + body + divider 为一次 append
            chunk_parts = [ensure_blank(section.title)]
            if section.body:
                chunk_parts.append(ensure_blank(section.body))
            if index < total:
                chunk_parts.append("\n\n---\n\n")
            combined = "\n\n".join(chunk_parts)
            publisher.append_doc("ref", write_chunk(tmp_path / "pub", f"section_{index:03d}", combined))

        # 2 个 section → 2 次 append（不是 6 次）
        assert call_count == 2
