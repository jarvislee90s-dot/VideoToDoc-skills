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
