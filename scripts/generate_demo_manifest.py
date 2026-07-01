import json
from pathlib import Path

REPO = "jarvislee90s-dot/VideoToDoc-skills"
BRANCH = "main"
DIR = "demo-assets/spacex"
BASE = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/{DIR}"

def main():
    root = Path(DIR)
    slides = sorted(p.name for p in (root / "selected_slides").glob("*.png"))
    manifest = {
        "baseUrl": BASE,
        "summary": f"{BASE}/SpaceX上市，背后在玩什么资本游戏_总结_20260630_231231.md",
        "lecture": f"{BASE}/SpaceX上市，背后在玩什么资本游戏_讲义_整理版_20260630_232710.md",
        "mindmap": f"{BASE}/SpaceX上市，背后在玩什么资本游戏_思维导图_渲染_20260630_232710.png",
        "transcript": f"{BASE}/transcript.json",
        "docx": f"{BASE}/SpaceX上市，背后在玩什么资本游戏_讲义_20260630_232710.docx",
        "slides": [f"{BASE}/selected_slides/{name}" for name in slides],
        "feishuUrl": "https://bcniplbzchv5.feishu.cn/docx/VtMldBO8koF4xTxuOQlck9Zfn2e",
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print("manifest.json 已生成")

if __name__ == "__main__":
    main()
