import json
from pathlib import Path

def test_manifest_exists_and_has_required_keys():
    manifest_path = Path("demo-assets/spacex/manifest.json")
    assert manifest_path.exists(), "manifest.json 应该存在"
    data = json.loads(manifest_path.read_text())
    required = {"baseUrl", "summary", "lecture", "mindmap", "transcript", "docx", "slides", "feishuUrl"}
    assert required.issubset(data.keys()), f"缺少键: {required - data.keys()}"
    assert len(data["slides"]) >= 8, "至少应有 8 张截图 URL"
