"""videotodoc 包入口，支持 python3 -m videotodoc 调用。"""
import sys

# Windows 控制台默认 GBK，脚本含 emoji 输出，强制 UTF-8 避免 UnicodeEncodeError
if sys.platform == "win32":
    for _s in (sys.stdout, sys.stderr):
        if _s and hasattr(_s, "reconfigure"):
            try:
                _s.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

from videotodoc.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
