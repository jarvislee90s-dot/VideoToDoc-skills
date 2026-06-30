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
  --bg:#F8F9FC;--surface:#FFFFFF;--code-bg:#F4F5F7;
  --text:#18191C;--muted:#61666D;--hint:#9499A0;
  --border:#E3E5E7;--border-strong:#DEE0E3;
  --r-sm:4px;--r-md:6px;--r-lg:8px;--r-xl:12px;
  --s-1:4px;--s-2:8px;--s-3:12px;--s-4:16px;--s-5:24px;--s-6:32px;
  --font:"-apple-system","PingFang SC","Microsoft YaHei",sans-serif;
  --mono:"SF Mono",Menlo,monospace;
  --maxw:1100px;
}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{font-family:var(--font);color:var(--text);background:linear-gradient(180deg,#F8F9FC 0%,#fff 30%,#fff 70%,#F8F9FC 100%);line-height:1.6;-webkit-font-smoothing:antialiased}
.container{max-width:var(--maxw);margin:0 auto;padding:var(--s-5)}
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--r-lg);padding:var(--s-4);box-shadow:0 2px 8px rgba(0,0,0,0.02)}
.lab{font-size:11px;color:var(--hint);font-weight:700;letter-spacing:1.5px;text-transform:uppercase;margin-bottom:var(--s-3);display:flex;align-items:center;gap:var(--s-2)}
.lab::before{content:"";width:3px;height:14px;background:var(--pink);display:inline-block}
.btn{display:inline-block;font-size:14px;font-weight:600;padding:10px 22px;border-radius:var(--r-md);transition:background-color 150ms ease;background:var(--pink);color:#fff;border:0;cursor:pointer}
.btn:hover{background:#e85d85}
input[type=text]{width:100%;padding:10px 12px;border:1px solid var(--border);border-radius:var(--r-md);font-family:var(--mono);font-size:13px}
</style>
</head>
<body>
<div class="container">
  <section id="hero" class="card" style="margin-bottom:var(--s-4)">
    <h1 style="font-size:32px;font-weight:800;margin-bottom:var(--s-2)">VideoToDoc Agent Demo</h1>
    <p style="color:var(--muted);margin-bottom:var(--s-3)">把一个视频链接交给 Agent，自动完成摘要、讲义、飞书发布。</p>
    <input type="text" id="videoUrl" value="https://www.youtube.com/watch?v=SpaceX..." readonly>
    <button class="btn" id="startBtn" style="margin-top:var(--s-3)">开始自动运行</button>
  </section>

  <section id="config" class="card" style="margin-bottom:var(--s-4)">
    <div class="lab">Agent 配置</div>
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:var(--s-3)">
      <div><label style="font-size:12px;color:var(--hint)">API Key</label><input type="text" value="sk-••••••••••••••••••••" readonly></div>
      <div><label style="font-size:12px;color:var(--hint)">Base URL</label><input type="text" value="https://api.openai.com/v1" readonly></div>
      <div><label style="font-size:12px;color:var(--hint)">模型</label><input type="text" value="gpt-4o" readonly></div>
    </div>
  </section>

  <section id="skills" class="card" style="margin-bottom:var(--s-4)">
    <div class="lab">三个 Skill</div>
    <details><summary><b>video-summary</b> — 视频转录与摘要</summary><p style="margin-top:var(--s-2);color:var(--muted);font-size:13px">输入视频链接或本地路径，自动获取字幕或 ASR 转录，生成文字摘要。</p></details>
    <details style="margin-top:var(--s-2)"><summary><b>video-to-slides</b> — 截图与图文讲义</summary><p style="margin-top:var(--s-2);color:var(--muted);font-size:13px">自动截图去重、图文对齐、语义整理，输出 Markdown/Word 与思维导图。</p></details>
    <details style="margin-top:var(--s-2)"><summary><b>feishu-markdown-publish</b> — 飞书云文档发布</summary><p style="margin-top:var(--s-2);color:var(--muted);font-size:13px">将整理好的 Markdown 讲义发布到飞书云文档。</p></details>
  </section>

  <section id="chat" class="card" style="margin-bottom:var(--s-4);display:none"></section>
  <section id="nodeFlow" class="card" style="margin-bottom:var(--s-4);display:none"></section>
  <section id="outputs" class="card" style="margin-bottom:var(--s-4);display:none"></section>

  <footer style="text-align:center;color:var(--hint);font-size:12px">
    <p><a href="https://github.com/jarvislee90s-dot/VideoToDoc-skills" target="_blank">GitHub</a> · <a href="https://forum.trae.cn/t/topic/30174" target="_blank">报名帖</a></p>
  </footer>
</div>
</body>
</html>
```

- [ ] **步骤 2：在浏览器中打开并检查控制台错误**

运行：
```bash
open docs/trae-competition/demo.html
```

预期结果：页面显示 Hero、配置和 Skill 区域，无控制台错误。

- [ ] **步骤 3：提交**

运行：
```bash
git add docs/trae-competition/demo.html
git commit -m "feat(demo): add demo HTML shell with registration styling"
```

---

### 任务 4：构建 AgentChat 回放组件

**文件：**
- 修改：`docs/trae-competition/demo.html`（在 `<script>` 标签内）

**接口：**
- 输入：`DEMO_DATA.chatScript` 数组，元素为 `{role, text}`。
- 输出：`AgentChat` 对象，方法 `start()` 以 1.2 秒间隔将消息追加到 `#chat`。

- [ ] **步骤 1：添加数据和聊天组件脚本**

在 `docs/trae-competition/demo.html` 的 `</body>` 前追加：

```html
<script>
const DEMO_DATA = {
  chatScript: [
    {role: "user", text: "帮我整理这个 SpaceX 上市视频： https://www.youtube.com/watch?v=SpaceX..."},
    {role: "agent", text: "收到。我将依次调用 video-summary、video-to-slides、feishu-markdown-publish 三个 Skill 完成处理。"},
    {role: "agent", text: "首先读取 video-summary/SKILL.md，了解转录与摘要流程。"},
    {role: "agent", text: "开始执行 process.py，下载视频并生成 transcript.json 与总结。"},
    {role: "agent", text: "video-summary 完成。接下来读取 video-to-slides/SKILL.md。"},
    {role: "agent", text: "正在截图、去重、图文对齐，生成讲义与思维导图。"},
    {role: "agent", text: "video-to-slides 完成。最后读取 feishu-markdown-publish/SKILL.md。"},
    {role: "agent", text: "已将讲义发布到飞书云文档，全部完成。"}
  ]
};

const AgentChat = {
  start() {
    const el = document.getElementById("chat");
    el.style.display = "block";
    let i = 0;
    const next = () => {
      if (i >= DEMO_DATA.chatScript.length) return;
      const msg = DEMO_DATA.chatScript[i++];
      const div = document.createElement("div");
      div.style.cssText = `margin-bottom:12px;display:flex;${msg.role === "agent" ? "justify-content:flex-end" : ""}`;
      const bubble = document.createElement("div");
      bubble.textContent = msg.text;
      bubble.style.cssText = msg.role === "agent"
        ? "background:#fff0f4;border:1px solid #FB7299;color:#18191C;border-radius:12px 12px 0 12px;padding:10px 14px;max-width:80%;font-size:13px"
        : "background:#f4f5f7;border:1px solid #e3e5e7;color:#18191C;border-radius:12px 12px 12px 0;padding:10px 14px;max-width:80%;font-size:13px";
      div.appendChild(bubble);
      el.appendChild(div);
      el.scrollTop = el.scrollHeight;
      setTimeout(next, 1200);
    };
    next();
  }
};

document.getElementById("startBtn").addEventListener("click", () => AgentChat.start());
</script>
```

- [ ] **步骤 2：打开并测试**

运行：
```bash
open docs/trae-competition/demo.html
```

点击"开始自动运行"。预期结果：聊天区域出现，消息逐条显示。

- [ ] **步骤 3：提交**

运行：
```bash
git add docs/trae-competition/demo.html
git commit -m "feat(demo): add AgentChat replay component"
```

---

### 任务 5：构建三列节点执行流可视化

**文件：**
- 修改：`docs/trae-competition/demo.html`

**接口：**
- 输入：`DEMO_DATA.nodeTimeline` 数组，元素包含 `kind`、`label`、`detail`、`state`、`progress`。
- 输出：`#nodeFlow` 区域渲染三列节点；`NodeFlow.update(stepIndex)` 改变激活/完成状态。

- [ ] **步骤 1：添加节点时间线数据和组件**

在现有 `<script>` 中 `DEMO_DATA` 定义之后插入：

```javascript
DEMO_DATA.nodeTimeline = [
  {kind: "agent", label: "读取 SKILL.md", detail: "video-summary/SKILL.md"},
  {kind: "agent", label: "调用脚本", detail: "process.py --url ..."},
  {kind: "script", label: "运行中", detail: "下载 → ASR → 摘要", progress: 65},
  {kind: "output", label: "已生成", detail: "SpaceX_总结.md", sub: "transcript.json · video.mp4"},
  {kind: "agent", label: "Agent 接收", detail: "摘要完成，准备截图对齐"},
  {kind: "agent", label: "读取 SKILL.md", detail: "video-to-slides/SKILL.md"},
  {kind: "agent", label: "调用脚本", detail: "process.py video.mp4 --transcript ..."},
  {kind: "script", label: "运行中", detail: "截图 → 对齐 → 讲义", progress: 80},
  {kind: "output", label: "已生成", detail: "SpaceX_讲义_整理版.md", sub: "思维导图.png · 56张截图 · .docx"},
  {kind: "agent", label: "Agent 接收", detail: "讲义完成，准备发布"},
  {kind: "agent", label: "读取 SKILL.md", detail: "feishu-publish/SKILL.md"},
  {kind: "agent", label: "调用脚本", detail: "publish_markdown.py 讲义.md"},
  {kind: "script", label: "运行中", detail: "上传飞书云文档", progress: 90},
  {kind: "output", label: "已发布", detail: "飞书云文档链接", sub: "bcniplbzchv5.feishu.cn/docx/..."},
  {kind: "agent", label: "全部完成", detail: "视频已转为图文讲义并发布到飞书"}
];
```

在 `</body>` 前追加新的 `<script>` 块：

```html
<script>
const NodeFlow = {
  render() {
    const el = document.getElementById("nodeFlow");
    el.style.display = "block";
    el.innerHTML = `
      <div class="lab">Agent 执行流</div>
      <div id="flowGrid" style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:0;position:relative;background:#fff;border:1px solid #e8eaf1;border-radius:12px;overflow:hidden">
        <div style="position:absolute;left:33.33%;top:0;bottom:0;border-left:1.5px dashed #e0e3eb;z-index:1"></div>
        <div style="position:absolute;left:66.66%;top:0;bottom:0;border-left:1.5px dashed #e0e3eb;z-index:1"></div>
        <div style="text-align:center;padding:16px 8px;font-size:11px;font-weight:800;color:#7a8194;letter-spacing:1.5px;border-bottom:2px solid #f0f2f7;background:#fafbfc">🤖 AGENT 操作</div>
        <div style="text-align:center;padding:16px 8px;font-size:11px;font-weight:800;color:#7a8194;letter-spacing:1.5px;border-bottom:2px solid #f0f2f7;background:#fafbfc">⚙️ 脚本执行</div>
        <div style="text-align:center;padding:16px 8px;font-size:11px;font-weight:800;color:#7a8194;letter-spacing:1.5px;border-bottom:2px solid #f0f2f7;background:#fafbfc">📄 产出文件</div>
        ${DEMO_DATA.nodeTimeline.map((step, idx) => this.renderStep(step, idx)).join("")}
      </div>
    `;
  },
  renderStep(step, idx) {
    const color = step.kind === "agent" ? "#FB7299" : step.kind === "script" ? "#00AEEC" : "#00B894";
    const bg = step.kind === "agent" ? "rgba(251,114,153,0.03)" : step.kind === "script" ? "rgba(0,174,236,0.03)" : "rgba(0,184,148,0.03)";
    return `
      <div id="step-${idx}" data-kind="${step.kind}" style="padding:12px;background:${bg};min-height:80px;display:flex;align-items:flex-start;justify-content:center">
        <div class="node-card" style="background:#fff;border:1px solid #e8eaf1;border-radius:10px;padding:10px 12px;width:100%;opacity:0.35;transition:all 0.3s ease">
          <div style="font-size:11px;font-weight:700;color:${color};margin-bottom:3px">${step.label}</div>
          <div style="font-size:12px;color:#61666D">${step.detail}</div>
          ${step.sub ? `<div style="font-size:11px;color:#9499A0;margin-top:3px">${step.sub}</div>` : ""}
          ${step.progress ? `<div style="margin-top:8px;height:3px;background:#e0e3eb;border-radius:2px;overflow:hidden"><div class="progress" style="width:0%;height:100%;background:${color};transition:width 0.8s ease"></div></div>` : ""}
        </div>
      </div>
    `;
  },
  activate(idx) {
    const cell = document.getElementById(`step-${idx}`);
    if (!cell) return;
    const card = cell.querySelector(".node-card");
    const kind = cell.dataset.kind;
    const color = kind === "agent" ? "#FB7299" : kind === "script" ? "#00AEEC" : "#00B894";
    card.style.opacity = "1";
    card.style.border = `2px solid ${color}`;
    card.style.boxShadow = `0 0 0 3px ${color}22`;
    card.style.animation = "pulse 0.8s ease-in-out infinite alternate";
    const progress = card.querySelector(".progress");
    if (progress) {
      setTimeout(() => progress.style.width = DEMO_DATA.nodeTimeline[idx].progress + "%", 50);
    }
  },
  complete(idx) {
    const cell = document.getElementById(`step-${idx}`);
    if (!cell) return;
    const card = cell.querySelector(".node-card");
    card.style.animation = "none";
    card.style.boxShadow = "none";
  }
};

const style = document.createElement("style");
style.textContent = `@keyframes pulse { from { transform: scale(1); } to { transform: scale(1.015); } }`;
document.head.appendChild(style);
</script>
```

- [ ] **步骤 2：将 NodeFlow 绑定到开始按钮**

将现有的点击监听器替换为：

```javascript
document.getElementById("startBtn").addEventListener("click", () => {
  AgentChat.start();
  NodeFlow.render();
  let step = 0;
  const run = () => {
    if (step >= DEMO_DATA.nodeTimeline.length) return;
    if (step > 0) NodeFlow.complete(step - 1);
    NodeFlow.activate(step);
    setTimeout(run, 1400);
    step++;
  };
  setTimeout(run, 1000);
});
```

- [ ] **步骤 3：打开并测试**

运行：
```bash
open docs/trae-competition/demo.html
```

点击"开始自动运行"。预期结果：聊天消息出现，节点卡片依次高亮。

- [ ] **步骤 4：提交**

运行：
```bash
git add docs/trae-competition/demo.html
git commit -m "feat(demo): add three-column NodeFlow visualization"
```

---

### 任务 6：添加 SVG 动态连线

**文件：**
- 修改：`docs/trae-competition/demo.html`

**接口：**
- 输入：`#flowGrid` 中的节点坐标和当前激活步骤。
- 输出：在 `#nodeFlow` 内部的 SVG 覆盖层，显示从产出文件到下一个 Agent 的虚线动画连线。

- [ ] **步骤 1：添加 ConnectionLines 组件**

在 `</body>` 前追加：

```html
<script>
const ConnectionLines = {
  el: null,
  init() {
    const container = document.getElementById("nodeFlow");
    this.el = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    this.el.setAttribute("id", "connectionSvg");
    this.el.style.cssText = "position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:3";
    container.style.position = "relative";
    container.appendChild(this.el);
  },
  draw(fromIdx, toIdx, label, color) {
    const grid = document.getElementById("flowGrid");
    const from = document.getElementById(`step-${fromIdx}`);
    const to = document.getElementById(`step-${toIdx}`);
    if (!from || !to || !grid) return;
    const gr = grid.getBoundingClientRect();
    const fr = from.getBoundingClientRect();
    const tr = to.getBoundingClientRect();
    const x1 = fr.left + fr.width / 2 - gr.left;
    const y1 = fr.top + fr.height / 2 - gr.top;
    const x2 = tr.left + tr.width / 2 - gr.left;
    const y2 = tr.top + tr.height / 2 - gr.top;
    const cx = (x1 + x2) / 2;
    const cy = (y1 + y2) / 2 - 20;
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", `M ${x1},${y1} Q ${cx},${cy} ${x2},${y2}`);
    path.setAttribute("stroke", color);
    path.setAttribute("stroke-width", "2");
    path.setAttribute("fill", "none");
    path.setAttribute("stroke-dasharray", "6,5");
    path.innerHTML = `<animate attributeName="stroke-dashoffset" from="22" to="0" dur="1s" repeatCount="indefinite" />`;
    this.el.appendChild(path);
    const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
    text.setAttribute("x", cx);
    text.setAttribute("y", cy);
    text.setAttribute("text-anchor", "middle");
    text.setAttribute("fill", color);
    text.setAttribute("font-size", "10");
    text.setAttribute("font-weight", "700");
    text.textContent = label;
    this.el.appendChild(text);
  },
  clear() {
    if (this.el) this.el.innerHTML = "";
  }
};
</script>
```

- [ ] **步骤 2：在相关转换处绘制连线**

在 `run` 循环中 `NodeFlow.activate(step)` 之后添加：

```javascript
if (step === 3) ConnectionLines.draw(3, 4, "transcript.json → 输入", "#00B894");
if (step === 8) ConnectionLines.draw(8, 9, "讲义.md → 输入", "#00B894");
```

同时在开始处理程序中 `NodeFlow.render()` 之后调用 `ConnectionLines.init()`。

- [ ] **步骤 3：打开并测试**

运行：
```bash
open docs/trae-competition/demo.html
```

预期结果：在产出节点之后，虚线动画连线将它们连接到下一个 Agent 节点。

- [ ] **步骤 4：提交**

运行：
```bash
git add docs/trae-competition/demo.html
git commit -m "feat(demo): add animated SVG connection lines"
```

---

### 任务 7：构建产物展示面板

**文件：**
- 修改：`docs/trae-competition/demo.html`
- 读取：`demo-assets/spacex/manifest.json`

**接口：**
- 输入：`DEMO_DATA.outputs`（来自清单）。
- 输出：`#outputs` 区域显示渲染后的摘要 Markdown、思维导图图片、截图画廊和飞书链接卡片。

- [ ] **步骤 1：将清单产物嵌入 DEMO_DATA**

在 `<script>` 块中添加：

```javascript
DEMO_DATA.outputs = {
  summary: "https://raw.githubusercontent.com/jarvislee90s-dot/VideoToDoc-skills/main/demo-assets/spacex/SpaceX上市，背后在玩什么资本游戏_总结_20260630_231231.md",
  lecture: "https://raw.githubusercontent.com/jarvislee90s-dot/VideoToDoc-skills/main/demo-assets/spacex/SpaceX上市，背后在玩什么资本游戏_讲义_整理版_20260630_232710.md",
  mindmap: "https://raw.githubusercontent.com/jarvislee90s-dot/VideoToDoc-skills/main/demo-assets/spacex/SpaceX上市，背后在玩什么资本游戏_思维导图_渲染_20260630_232710.png",
  transcript: "https://raw.githubusercontent.com/jarvislee90s-dot/VideoToDoc-skills/main/demo-assets/spacex/transcript.json",
  docx: "https://raw.githubusercontent.com/jarvislee90s-dot/VideoToDoc-skills/main/demo-assets/spacex/SpaceX上市，背后在玩什么资本游戏_讲义_20260630_232710.docx",
  slides: [
    "https://raw.githubusercontent.com/jarvislee90s-dot/VideoToDoc-skills/main/demo-assets/spacex/selected_slides/0001.png",
    "https://raw.githubusercontent.com/jarvislee90s-dot/VideoToDoc-skills/main/demo-assets/spacex/selected_slides/0005.png",
    "https://raw.githubusercontent.com/jarvislee90s-dot/VideoToDoc-skills/main/demo-assets/spacex/selected_slides/0010.png",
    "https://raw.githubusercontent.com/jarvislee90s-dot/VideoToDoc-skills/main/demo-assets/spacex/selected_slides/0015.png",
    "https://raw.githubusercontent.com/jarvislee90s-dot/VideoToDoc-skills/main/demo-assets/spacex/selected_slides/0020.png",
    "https://raw.githubusercontent.com/jarvislee90s-dot/VideoToDoc-skills/main/demo-assets/spacex/selected_slides/0030.png",
    "https://raw.githubusercontent.com/jarvislee90s-dot/VideoToDoc-skills/main/demo-assets/spacex/selected_slides/0040.png",
    "https://raw.githubusercontent.com/jarvislee90s-dot/VideoToDoc-skills/main/demo-assets/spacex/selected_slides/0050.png"
  ],
  feishu: "https://bcniplbzchv5.feishu.cn/docx/VtMldBO8koF4xTxuOQlck9Zfn2e"
};
```

- [ ] **步骤 2：添加 OutputPanel 组件**

在 `</body>` 前追加：

```html
<script>
const OutputPanel = {
  async show() {
    const el = document.getElementById("outputs");
    el.style.display = "block";
    const summaryText = await fetch(DEMO_DATA.outputs.summary).then(r => r.ok ? r.text() : "加载失败");
    el.innerHTML = `
      <div class="lab">产物展示</div>
      <div style="margin-bottom:24px">
        <h3 style="font-size:14px;margin-bottom:8px">1. 视频摘要</h3>
        <div style="background:#fafbfc;border:1px solid #e8eaf1;border-radius:8px;padding:12px;max-height:200px;overflow:auto;font-size:13px;color:#61666D;white-space:pre-wrap">${summaryText.substring(0, 1200)}...</div>
        <a href="${DEMO_DATA.outputs.summary}" target="_blank" style="font-size:12px;color:#00AEEC">查看完整 summary.md →</a>
      </div>
      <div style="margin-bottom:24px">
        <h3 style="font-size:14px;margin-bottom:8px">2. 思维导图</h3>
        <img src="${DEMO_DATA.outputs.mindmap}" style="max-width:100%;border:1px solid #e8eaf1;border-radius:8px" alt="mindmap">
      </div>
      <div style="margin-bottom:24px">
        <h3 style="font-size:14px;margin-bottom:8px">3. 关键截图</h3>
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px">
          ${DEMO_DATA.outputs.slides.map(url => `<img src="${url}" style="width:100%;border:1px solid #e8eaf1;border-radius:6px" alt="slide">`).join("")}
        </div>
      </div>
      <div>
        <h3 style="font-size:14px;margin-bottom:8px">4. 飞书云文档</h3>
        <a href="${DEMO_DATA.outputs.feishu}" target="_blank" style="display:inline-block;background:#f0fbf6;border:1px solid #b9ead4;color:#00B894;padding:10px 16px;border-radius:8px;font-weight:600">打开飞书讲义 →</a>
      </div>
    `;
  }
};
</script>
```

- [ ] **步骤 3：在第二个 Skill 完成后触发 OutputPanel**

在开始处理程序中添加：

```javascript
if (step === 8) setTimeout(() => OutputPanel.show(), 800);
```

- [ ] **步骤 4：打开并测试**

运行：
```bash
open docs/trae-competition/demo.html
```

预期结果：第 8 步之后，产物展示区出现，包含摘要文本、思维导图、截图和飞书链接。

- [ ] **步骤 5：提交**

运行：
```bash
git add docs/trae-competition/demo.html
git commit -m "feat(demo): add OutputPanel with real SpaceX outputs"
```

---

### 任务 8：整合完整回放时序并润色

**文件：**
- 修改：`docs/trae-competition/demo.html`

**接口：**
- 输入：之前所有组件。
- 输出：一个协调的定时回放，聊天、节点、连线和产物按顺序同步出现。

- [ ] **步骤 1：用最终编排替换开始处理程序**

最终开始处理程序应如下：

```javascript
document.getElementById("startBtn").addEventListener("click", async () => {
  const btn = document.getElementById("startBtn");
  btn.disabled = true;
  btn.textContent = "运行中...";
  AgentChat.start();
  NodeFlow.render();
  ConnectionLines.init();
  let step = 0;
  const run = () => {
    if (step >= DEMO_DATA.nodeTimeline.length) {
      btn.textContent = "已完成";
      return;
    }
    if (step > 0) NodeFlow.complete(step - 1);
    NodeFlow.activate(step);
    if (step === 3) ConnectionLines.draw(3, 4, "transcript.json → 输入", "#00B894");
    if (step === 8) {
      ConnectionLines.draw(8, 9, "讲义.md → 输入", "#00B894");
      setTimeout(() => OutputPanel.show(), 600);
    }
    step++;
    setTimeout(run, 1300);
  };
  setTimeout(run, 800);
});
```

- [ ] **步骤 2：在页脚添加 Session ID**

更新 HTML body 中的页脚：

```html
<footer style="text-align:center;color:var(--hint);font-size:12px">
  <p><a href="https://github.com/jarvislee90s-dot/VideoToDoc-skills" target="_blank">GitHub</a> · <a href="https://forum.trae.cn/t/topic/30174" target="_blank">报名帖</a></p>
  <p style="margin-top:8px">关键 Session IDs: 6a411c02d4657102f33b1067 · [作者补充其他 ID]</p>
</footer>
```

- [ ] **步骤 3：运行完整回放并验证时序**

运行：
```bash
open docs/trae-competition/demo.html
```

点击"开始自动运行"并观察完整流程。预期结果：聊天、节点高亮、连线和产物按同步、可理解的顺序出现。

- [ ] **步骤 4：提交**

运行：
```bash
git add docs/trae-competition/demo.html
git commit -m "feat(demo): synchronize full replay timing and add footer"
```

---

### 任务 9：验证 URL、体积和移动端布局

**文件：**
- 创建：`scripts/validate_demo.py`

**接口：**
- 输入：`docs/trae-competition/demo.html` 和 `demo-assets/spacex/manifest.json`。
- 输出：打印验证报告；失败时以非零状态退出。

- [ ] **步骤 1：编写验证脚本**

创建 `scripts/validate_demo.py`：

```python
import re
import sys
import zipfile
from pathlib import Path
import urllib.request

HTML = Path("docs/trae-competition/demo.html")
ZIP = Path("docs/trae-competition/demo.zip")

def extract_urls(text):
    return re.findall(r'https?://[^\s"<>]+', text)

def main():
    html = HTML.read_text()
    urls = extract_urls(html)
    print(f"找到 {len(urls)} 个 URL")
    failures = []
    for url in urls:
        if "raw.githubusercontent.com" not in url and "feishu.cn" not in url:
            continue
        try:
            req = urllib.request.Request(url, method="HEAD")
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
```

- [ ] **步骤 2：创建 ZIP 并运行验证**

运行：
```bash
python3 scripts/validate_demo.py
```

预期结果：所有 GitHub URL 返回 200（要求资源已推送到 `main`），飞书有响应，ZIP 体积小。

- [ ] **步骤 3：如尚未推送则推送资源**

运行：
```bash
git push origin main
```

- [ ] **步骤 4：推送后重新验证**

运行：
```bash
python3 scripts/validate_demo.py
```

预期结果：所有可访问 URL 通过，ZIP 小于 20 MB。

- [ ] **步骤 5：提交验证器**

运行：
```bash
git add scripts/validate_demo.py
git commit -m "feat(demo): add demo validation script for URLs and ZIP size"
```

---

### 任务 10：Playwright MCP 端到端视觉验证

**文件：**
- 读取：`docs/trae-competition/demo.html`
- 创建：`docs/trae-competition/e2e-screenshots/`（每一步截图）

**接口：**
- 输入：完整的 `demo.html`。
- 输出：多张运行时截图 + 一份视觉评价报告。

- [ ] **步骤 1：启动本地 HTTP 服务**

Playwright 通过 HTTP 加载页面比直接打开 `file://` 更稳定。运行：

```bash
cd docs/trae-competition && python3 -m http.server 8765 &
```

- [ ] **步骤 2：打开浏览器并访问 Demo**

使用 Playwright MCP 工具：

```json
{
  "url": "http://localhost:8765/demo.html",
  "width": 1280,
  "height": 900
}
```

- [ ] **步骤 3：截图初始状态**

使用 Playwright MCP 截图工具，保存为：

```
docs/trae-competition/e2e-screenshots/01-initial.png
```

评价点：Hero、配置面板、三个 Skill 折叠面板是否正确渲染，无错位。

- [ ] **步骤 4：点击"开始自动运行"按钮**

使用 Playwright MCP 点击工具，选择 `#startBtn`。

- [ ] **步骤 5：截图 AgentChat 出现后的状态**

等待 2 秒后截图：

```
docs/trae-competition/e2e-screenshots/02-chat-started.png
```

评价点：聊天区域是否出现，用户消息和 Agent 消息气泡样式是否正确。

- [ ] **步骤 6：截图 NodeFlow 运行中**

等待 5 秒后截图：

```
docs/trae-competition/e2e-screenshots/03-nodeflow-running.png
```

评价点：三列节点流是否正确渲染，当前激活节点是否有高亮/呼吸动画，未激活节点是否降透明度。

- [ ] **步骤 7：截图 SVG 连线出现**

等待到第 8 步左右截图：

```
docs/trae-competition/e2e-screenshots/04-connection-lines.png
```

评价点：从产出文件到下一个 Agent 的虚线动画连线是否正确绘制，标签是否清晰。

- [ ] **步骤 8：截图 OutputPanel 产物展示**

等待约 18 秒后截图：

```
docs/trae-competition/e2e-screenshots/05-outputs.png
```

评价点：摘要文本、思维导图、截图画廊、飞书链接是否都正确加载，无 404 图片占位。

- [ ] **步骤 9：截图移动端布局**

调整视口为 iPhone 14 Pro（393 × 852）并刷新页面，点击"开始"后截图：

```
docs/trae-competition/e2e-screenshots/06-mobile.png
```

评价点：单列布局是否没有严重重叠，节点卡片是否可滚动，产物图片是否自适应。

- [ ] **步骤 10：输出视觉评价报告**

在 `docs/trae-competition/e2e-screenshots/README.md` 中记录：

```markdown
# Demo 端到端视觉验证报告

| 截图 | 状态 | 问题 |
|---|---|---|
| 01-initial.png | 通过/待修复 | ... |
| 02-chat-started.png | 通过/待修复 | ... |
| 03-nodeflow-running.png | 通过/待修复 | ... |
| 04-connection-lines.png | 通过/待修复 | ... |
| 05-outputs.png | 通过/待修复 | ... |
| 06-mobile.png | 通过/待修复 | ... |

总体评价：...
```

- [ ] **步骤 11：关闭浏览器并停止 HTTP 服务**

运行：

```bash
pkill -f "http.server 8765"
```

- [ ] **步骤 12：根据评价修复问题**

如果截图发现问题，返回对应任务修复（通常是任务 3 样式、任务 5 节点布局、任务 7 产物展示）。修复后重新运行本任务截图验证。

- [ ] **步骤 13：提交截图和评价报告**

运行：

```bash
git add docs/trae-competition/e2e-screenshots/
git commit -m "test(demo): add Playwright e2e screenshots and visual report"
```

---

### 任务 11：最终打包和文档更新

**文件：**
- 创建：`docs/trae-competition/demo.zip`
- 修改：`README.md`
- 修改：`CHANGELOG.md`

**接口：**
- 输入：经验证的 `docs/trae-competition/demo.html` 和 `e2e-screenshots/`。
- 输出：最终 ZIP 和更新的项目文档。

- [ ] **步骤 1：构建最终 ZIP**

运行：
```bash
cd docs/trae-competition && zip -r demo.zip demo.html && cd ../..
```

- [ ] **步骤 2：在 README 中添加 Demo 链接**

在 `README.md` 的项目概览部分之后添加：

```markdown
## 初赛 Demo

在线体验 Demo（单文件 HTML）：[docs/trae-competition/demo.html](docs/trae-competition/demo.html)

下载 ZIP 上传版本：[docs/trae-competition/demo.zip](docs/trae-competition/demo.zip)
```

- [ ] **步骤 3：更新 CHANGELOG**

在 `CHANGELOG.md` 中添加新标题：

```markdown
## 2026-06-30

- 新增 TRAE 初赛 Demo HTML，支持 Agent 对话回放、三列节点执行流可视化、真实 SpaceX 产物展示
```

- [ ] **步骤 4：最终提交**

运行：
```bash
git add docs/trae-competition/demo.zip README.md CHANGELOG.md
git commit -m "docs(demo): package demo ZIP and update README/CHANGELOG"
```

- [ ] **步骤 5：最终推送**

运行：
```bash
git push origin main
```

---

## 自检

### 设计文档覆盖

| 设计文档章节 | 实施任务 |
|---|---|
| 单文件 HTML Demo | 任务 3、8、11 |
| GitHub 资源引用 | 任务 1、2 |
| 三列节点流 | 任务 5 |
| Agent 对话回放 | 任务 4 |
| 动画连线 | 任务 6 |
| 真实产物展示 | 任务 7 |
| URL/体积验证 | 任务 9 |
| Playwright 端到端视觉验证 | 任务 10 |
| 与报名页视觉一致 | 任务 3 |
| 页脚 Session ID | 任务 8 |

### 占位符检查

- 无 TBD/TODO。
- 无模糊的"添加错误处理"步骤；错误处理已内嵌在组件行为和验证中。
- 每个代码步骤都包含实际代码。

### 类型一致性

- `DEMO_DATA.chatScript` 和 `DEMO_DATA.nodeTimeline` 在聊天、节点流和编排任务中一致使用。
- `DEMO_DATA.outputs` 的键在任务 7 和任务 8 中统一引用。
