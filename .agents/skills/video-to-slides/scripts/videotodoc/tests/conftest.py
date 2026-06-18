"""共享 fixture：把 videotodoc 包和 _shared 加入 sys.path。"""
import sys
from pathlib import Path

# conftest.py 位于 .../scripts/videotodoc/tests/conftest.py
# parents[2] = scripts/（含 videotodoc 包），parents[4] = skills/（含 _shared）
SCRIPTS_DIR = Path(__file__).resolve().parents[2]
SHARED_DIR = SCRIPTS_DIR.parents[1] / "_shared"
for p in (SCRIPTS_DIR, SHARED_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

# 飞书 publish.py 脚本目录（供 test_publish 导入）
FEISHU_SCRIPTS = Path(__file__).resolve().parents[4] / "feishu-markdown-publish" / "scripts"
if str(FEISHU_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(FEISHU_SCRIPTS))

# video-summary 脚本目录（供 test_bilibili 导入 process 模块）
VS_SCRIPTS = Path(__file__).resolve().parents[4] / "video-summary" / "scripts"
if str(VS_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(VS_SCRIPTS))
