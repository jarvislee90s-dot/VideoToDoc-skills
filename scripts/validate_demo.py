import re
import sys
import zipfile
from pathlib import Path
import urllib.request
from urllib.parse import quote

# 验证目标文件
HTML = Path("docs/trae-competition/demo.html")
ZIP = Path("docs/trae-competition/demo.zip")


def extract_urls(text):
    """从文本中提取 http/https URL 列表。"""
    return re.findall(r'https?://[^\s"<>]+', text)


def main():
    # 读取 demo.html 并提取所有 URL
    html = HTML.read_text()
    urls = extract_urls(html)
    print(f"找到 {len(urls)} 个 URL")

    # 校验 raw.githubusercontent.com 与 feishu.cn 链接的可访问性
    failures = []
    for url in urls:
        if "raw.githubusercontent.com" not in url and "feishu.cn" not in url:
            continue
        # 对非 ASCII 字符进行百分号编码，避免 urllib 抛出编码异常
        encoded_url = quote(url, safe="/:?&=")
        try:
            req = urllib.request.Request(encoded_url, method="HEAD")
            req.add_header("User-Agent", "Mozilla/5.0")
            with urllib.request.urlopen(req, timeout=20) as r:
                if r.status >= 400:
                    failures.append(f"{url} -> {r.status}")
                else:
                    print(f"OK {r.status} {url[:80]}...")
        except Exception as e:
            failures.append(f"{url} -> {e}")

    if failures:
        print("\n失败:")
        for f in failures:
            print(f)
        sys.exit(1)

    # 将 demo.html 打包为 ZIP 并检查体积是否小于 20 MB
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(HTML, "demo.html")
    size = ZIP.stat().st_size
    print(f"\nZIP 大小: {size / 1024:.1f} KB (限制 20 MB)")
    if size > 20 * 1024 * 1024:
        print("ZIP 超过 20 MB 限制")
        sys.exit(1)

    print("验证通过")


if __name__ == "__main__":
    main()
