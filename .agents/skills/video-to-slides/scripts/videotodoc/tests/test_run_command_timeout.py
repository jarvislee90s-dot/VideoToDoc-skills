from __future__ import annotations

import pytest

from ..utils import VideoToDocError, run_command


class TestRunCommandTimeout:
    def test_timeout_raises_video_to_doc_error(self) -> None:
        with pytest.raises(VideoToDocError) as exc_info:
            run_command(["sleep", "10"], timeout=1)
        msg = str(exc_info.value)
        assert "超时" in msg or "timeout" in msg.lower()
        assert "sleep" in msg
        assert "1" in msg

    def test_normal_command_completes_within_timeout(self) -> None:
        result = run_command(["echo", "hello"], timeout=5)
        assert result.returncode == 0
        assert "hello" in result.stdout

    def test_default_timeout_allows_quick_commands(self) -> None:
        result = run_command(["echo", "quick"])
        assert result.returncode == 0
        assert "quick" in result.stdout

    def test_timeout_error_includes_command_info(self) -> None:
        with pytest.raises(VideoToDocError) as exc_info:
            run_command(["sleep", "5"], timeout=1)
        msg = str(exc_info.value)
        assert "sleep 5" in msg or "sleep" in msg
