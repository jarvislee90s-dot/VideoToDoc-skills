# VideoToDoc 初赛 Demo HTML 实施计划

> **给执行 Agent：** 必须使用的子技能：superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans，按任务逐步实施。每个步骤使用复选框（`- [ ]`）语法跟踪进度。

**目标：** 构建一个单文件 HTML Demo，基于 SpaceX 样本回放 VideoToDoc Agent 的完整工作流，包含三列节点执行流可视化，并链接到真实的产物文件。

**架构：** 单个 HTML 文件内嵌 CSS、JavaScript 数据清单和组件逻辑。产物文件通过 GitHub 仓库的 `demo-assets/spacex/` 目录使用 raw.githubusercontent.com URL 引用，保持 HTML 体积小巧。一个 Python 验证脚本检查所有引用的 URL 可访问，且最终 ZIP 小于 20 MB。

**技术栈：** HTML5、CSS3、原生 JavaScript、SVG 连线、GitHub raw URL、Python 3 验证脚本。

## 全局约束

- Demo 必须是单个 HTML 文件，以 ZIP 形式上传至 TRAE 论坛（论坛限制 20 MB）。
- 不使用外部 JS/CSS 框架，所有内容内联在 HTML 中。
- 所有二进制资源（图片、视频、文档）必须通过 URL 引用，禁止 base64 内联。
- 视觉风格必须与报名 HTML 一致：B站浅色调，颜色 `#FB7299`（粉）、`#00AEEC`（蓝）、`#00B894`（绿），圆角卡片，微投影。
- SpaceX 样本产物必须先复制到 `demo-assets/spacex/` 并推送到 `main` 分支，HTML 才能引用它们。
- 飞书文档链接必须保持公开可访问；若不可访问，Demo 必须优雅降级。
- 回放是模拟的，浏览器中不会进行真实的 API 调用或 Python 执行。

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `demo-assets/spacex/` | `main` 分支上的目录，包含真实的 SpaceX 样本产物（Markdown、图片、JSON、docx、视频）。 |
| `demo-assets/spacex/manifest.json` | 机器可读的产物清单，记录每个文件及其 GitHub raw URL。 |
| `docs/trae-competition/demo.html` | 单文件 Demo（CSS + HTML + JS + 数据）。 |
| `scripts/generate_demo_manifest.py` | 根据本地跑批目录生成 `demo-assets/spacex/manifest.json`。 |
| `scripts/validate_demo.py` | 验证 Demo 中每个 URL 可访问，且 ZIP 小于 20 MB。 |
| `docs/superpowers/specs/2026-06-30-trae-demo-design.md` | 已批准的设计文档（只读参考）。 |

---

### 任务 1：将 SpaceX 样本产物复制到 GitHub 资源目录并立即推送

**文件：**
- 创建：`demo-assets/spacex/SpaceX上市，背后在玩什么资本游戏_总结_20260630_231231.md`
- 创建：`demo-assets/spacex/SpaceX上市，背后在玩什么资本游戏_讲义_整理版_20260630_232710.md`
- 创建：`demo-assets/spacex/SpaceX上市，背后在玩什么资本游戏_思维导图_渲染_20260630_232710.png`
- 创建：`demo-assets/spacex/transcript.json`
- 创建：`demo-assets/spacex/selected_slides/`（8–10 张精选 PNG）
- 创建：`demo-assets/spacex/SpaceX上市，背后在玩什么资本游戏_讲义_20260630_232710.docx`
- 复制源：`runs/SpaceX上市，背后在玩什么资本游戏_20260630_231231/`

**接口：**
- 输入：已有的本地跑批目录。
- 输出：`demo-assets/spacex/` 目录已提交并推送到 `main`，确保后续 HTML 引用时 raw URL 已可访问。

- [ ] **步骤 1：创建目标目录**

运行：
```bash
mkdir -p demo-assets/spacex/selected_slides
```

- [ ] **步骤 2：复制核心产物文件**

运行：
```bash
SRC="runs/SpaceX上市，背后在玩什么资本游戏_20260630_231231"
DST="demo-assets/spacex"
cp "$SRC/SpaceX上市，背后在玩什么资本游戏_总结_20260630_231231.md" "$DST/"
cp "$SRC/SpaceX上市，背后在玩什么资本游戏_讲义_整理版_20260630_232710.md" "$DST/"
cp "$SRC/SpaceX上市，背后在玩什么资本游戏_思维导图_渲染_20260630_232710.png" "$DST/"
cp "$SRC/transcript.json" "$DST/"
cp "$SRC/SpaceX上市，背后在玩什么资本游戏_讲义_20260630_232710.docx" "$DST/"
```

- [ ] **步骤 3：精选 8–10 张代表性截图**

运行：
```bash
SRC="runs/SpaceX上市，背后在玩什么资本游戏_20260630_231231/selected_slides_audit_0.06_8_15_False"
DST="demo-assets/spacex/selected_slides"
for f in 0001.png 0005.png 0010.png 0015.png 0020.png 0030.png 0040.png 0050.png; do
  cp "$SRC/$f" "$DST/" || true
done
```

- [ ] **步骤 4：验证文件已存在**

运行：
```bash
find demo-assets/spacex -type f | sort
```

预期结果：至少 12 个文件，包括摘要 Markdown、思维导图 PNG、transcript.json、docx 和 8 张 PNG 截图。

- [ ] **步骤 5：立即提交并推送到 GitHub**

运行：
```bash
git add demo-assets/spacex/
git commit -m "chore(demo): add SpaceX sample outputs for TRAE competition demo"
git push origin main
```

预期结果：资源在 `https://raw.githubusercontent.com/jarvislee90s-dot/VideoToDoc-skills/main/demo-assets/spacex/` 上可访问，早于 HTML 引用它们的时间。

---

### 任务 2：生成 Demo 资源清单

**文件：**
- 创建：`scripts/generate_demo_manifest.py`
- 创建：`demo-assets/spacex/manifest.json`

**接口：**
- 输入：`demo-assets/spacex/` 中的文件。
- 输出：`demo-assets/spacex/manifest.json`，包含键 `summary`、`lecture`、`mindmap`、`transcript`、`docx`、`slides[]`、`video`、`baseUrl`。

- [ ] **步骤 1：编写失败测试**

创建 `tests/test_demo_manifest.py`：

```python
import json
from pathlib import Path

def test_manifest_exists_and_has_required_keys():
    manifest_path = Path("demo-assets/spacex/manifest.json")
    assert manifest_path.exists(), "manifest.json 应该存在"
    data = json.loads(manifest_path.read_text())
    required = {"baseUrl", "summary", "lecture", "mindmap", "transcript", "docx", "slides", "feishuUrl"}
    assert required.issubset(data.keys()), f"缺少键: {required - data.keys()}"
    assert len(data["slides"]) >= 8, "至少应有 8 张截图 URL"
```

- [ ] **步骤 2：运行测试确认失败**

运行：
```bash
pytest tests/test_demo_manifest.py -v
```

预期结果：失败，提示 `manifest.json 应该存在`。

- [ ] **步骤 3：编写清单生成器**

创建 `scripts/generate_demo_manifest.py`：

```python
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
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print("manifest.json 已生成")

if __name__ == "__main__":
    main()
```

- [ ] **步骤 4：运行生成器**

运行：
```bash
python3 scripts/generate_demo_manifest.py
```

- [ ] **步骤 5：运行测试确认通过**

运行：
```bash
pytest tests/test_demo_manifest.py -v
```

预期结果：通过。

- [ ] **步骤 6：提交**

运行：
```bash
git add scripts/generate_demo_manifest.py tests/test_demo_manifest.py demo-assets/spacex/manifest.json
git commit -m "feat(demo): add manifest generator for demo assets"
```

---

### 任务 3：创建 HTML 外壳并复用报名页样式

**文件：**
- 创建：`docs/trae-competition/demo.html`

**接口：**
- 输入：设计文档第 4.1 节（视觉风格）。
- 输出：`demo.html`，包含 Hero、配置面板和 Skill 提示词区域，能在浏览器中正确渲染。

- [ ] **步骤 1：创建最小 HTML 文件**

创建 `docs/trae-competition/demo.html`，初始内容如下：

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>VideoToDoc Demo · 视频一键变图文讲义</title>
<style>
:root{
  --pink:#FB7299;--blue:#00AEEC;--green:#00B894;
  --bg:#F8F9FC;--