# TRAE AI 创造力大赛报名 HTML 实现计划

> **面向 AI 代理的工作者：** 必需子技能:使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标:** 为 TRAE AI 创造力大赛构建一份单文件 HTML 报名作品(B 站浅色调性 + 抽屉交互),配套一份可粘贴的报名帖 md 文本。

**架构:** 7 段叙事流单页滚动 HTML;粉 #FB7299 + 蓝 #00AEEC 纯色,严禁渐变;§5 三步流程用手风琴抽屉(默认展开第 1 步);§6 用真实跑批产物 base64 内联展示。

**技术栈:** 单文件 HTML(内联 CSS + vanilla JS + base64 PNG),系统字体栈,无任何外部依赖。

**输入参考:**
- 规格: `docs/superpowers/specs/2026-06-17-trae-ai-competition-html-design.md`
- 真实产物: `runs/AI圈大乱!MiniMax M3 ... 即将开源;..._ AI日报_20260615_092737/`
- GitHub: <https://github.com/jarvislee90s-dot/VideoToDoc-skills>

---

## 文件结构

```
docs/trae-competition/
├── index.html          # 报名作品(单文件,内联所有资源)
├── 报名帖.md           # 配套报名帖正文(四部分+附录)
└── assets/             # base64 编码前的样例图(供构建时使用)
    ├── slide-1.png     # 从 selected_slides 选定的 3 张讲义截图
    ├── slide-2.png
    ├── slide-3.png
    └── mindmap.png     # 思维导图缩略
```

产物对应关系:
- `index.html` → 上传至社区报名帖(单文件 ≤ 20MB,目标 < 3MB)
- `报名帖.md` → 用户复制正文到 TRAE 社区发帖
- `assets/` → 不上传,作为构建 `index.html` 的中间资源,完成后可保留作为产物参考

---

## 任务列表

### 任务 1: 选定 §6 样例图

**文件:**
- 创建: `docs/trae-competition/assets/slide-1.png` (从 RUN2 `selected_slides_audit_0.06_8_15_False/0001.png`)
- 创建: `docs/trae-competition/assets/slide-2.png` (从 RUN2 `.../0004.png`)
- 创建: `docs/trae-competition/assets/slide-3.png` (从 RUN2 `.../0007.png`)
- 创建: `docs/trae-competition/assets/mindmap.png` (从 RUN2 `mindmap.png`)

- [ ] **步骤 1: 选 3 张代表性 slides**

选择标准: 优先选 < 350KB 的(总 base64 后约 1.3MB)。候选清单(已探查):
- `0001.png` 520KB — Anthropic 认错(主题相关)
- `0002.png` 583KB
- `0003.png` 1.1MB
- `0004.png` 298KB — OpenAI 降价(主题相关)
- `0006.png` 315KB
- `0007.png` 283KB — Midjourney/MiniMax(主题相关)

选定: `0001.png` + `0004.png` + `0007.png`(都是 AI 日报主题相关,且总原图 1.1MB,base64 后 ~1.5MB)

```bash
RUN="/Users/jarvis/Documents/VideoToDoc-skills/runs/AI圈大乱!MiniMax M3 即将开源;Anthropic 低头认错,OpenAI 认输甩卖!_ AI日报_20260615_092737"
cp "$RUN/selected_slides_audit_0.06_8_15_False/0001.png" /Users/jarvis/Documents/VideoToDoc-skills/docs/trae-competition/assets/slide-1.png
cp "$RUN/selected_slides_audit_0.06_8_15_False/0004.png" /Users/jarvis/Documents/VideoToDoc-skills/docs/trae-competition/assets/slide-2.png
cp "$RUN/selected_slides_audit_0.06_8_15_False/0007.png" /Users/jarvis/Documents/VideoToDoc-skills/docs/trae-competition/assets/slide-3.png
cp "$RUN/mindmap.png" /Users/jarvis/Documents/VideoToDoc-skills/docs/trae-competition/assets/mindmap.png
```

- [ ] **步骤 2: 验证文件已复制**

```bash
ls -la /Users/jarvis/Documents/VideoToDoc-skills/docs/trae-competition/assets/
du -sh /Users/jarvis/Documents/VideoToDoc-skills/docs/trae-competition/assets/
```

预期: 4 个文件,总大小约 1.2MB

- [ ] **步骤 3: Commit**

```bash
git add docs/trae-competition/assets/
git commit -m "feat(trae-comp): select 3 sample slides + mindmap for HTML showcase"
```

---

### 任务 2: 写出 §6 样例文字(Markdown 节选)

**文件:**
- 创建: `docs/trae-competition/sample-text.md`(作为构建时复制粘贴的源,非最终产物)

- [ ] **步骤 1: 抽取讲义关键段落**

从 RUN2 `video_讲义_整理版_20260615_092737.md` 中选取最能体现"语义整理效果"的 2-3 段(每段 ≤ 200 字),展示 AI 自动整理后的结构化讲义 vs 原始 ASR 转录。

```markdown
# §6 样例讲义节选(最终粘贴到 index.html 的 §6)

## 案例标题: AI 日报 0611 · 一夜变天

### 原始转录(节选)
> 嗯那个今天我们来聊一下就是啊最近这个 AI 圈的一些大事件 首先是 Anthropic 这个事 嗯 之前有报道说他们静默降智 然后他们现在说啊 我们不再这样做了 我们要转为可见的 就是说...这个...

### 整理后(VideoToDoc 输出)
**Anthropic 撤回静默降智,转为可见机制**

Anthropic 撤回了对 Claude 5 系列模型"对大模型开发相关请求进行静默破坏"的策略,承认此前不透明的做法是错误的权衡。从本周起,相关防护机制转为可见:系统会明确拒绝这些请求,或回退至较弱的 OP4.8 模型;API 端也会返回具体原因。
```

- [ ] **步骤 2: 验证样例文本已写好**

```bash
wc -c /Users/jarvis/Documents/VideoToDoc-skills/docs/trae-competition/sample-text.md
```

预期: 约 400-600 字符

- [ ] **步骤 3: Commit**

```bash
git add docs/trae-competition/sample-text.md
git commit -m "docs(trae-comp): add §6 sample text excerpt for showcase"
```

---

### 任务 3: 生成 base64 数据 URI(用于 §6 内联)

**文件:**
- 创建: `docs/trae-competition/assets/embedded.json` (含 4 个 base64 data URI 字符串,供 index.html 引用)
- 创建: `scripts/build_embedded.py`(一次性构建脚本,生成 embedded.json)

- [ ] **步骤 1: 写构建脚本**

```python
#!/usr/bin/env python3
"""将样例图编码为 base64 data URI,供 index.html 直接嵌入使用。"""
import base64
import json
import sys
from pathlib import Path

ASSETS = Path(__file__).parent.parent / "docs/trae-competition" / "assets"
OUT = ASSETS / "embedded.json"

ITEMS = [
    ("slide-1", "讲义截图 1: Anthropic 撤回静默降智"),
    ("slide-2", "讲义截图 2: OpenAI 大幅降价"),
    ("slide-3", "讲义截图 3: MiniMax M3 开源与 Midjourney V8.1"),
    ("mindmap", "思维导图: AI 日报 0611 主题结构"),
]

def encode(p: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()

result = {}
for key, alt in ITEMS:
    png = ASSETS / f"{key}.png"
    if not png.exists():
        print(f"missing: {png}", file=sys.stderr); sys.exit(1)
    result[key] = {"alt": alt, "data": encode(png), "size": png.stat().st_size}
    print(f"  {key}: {png.stat().st_size} bytes -> {len(result[key]['data'])} b64 chars")

OUT.write_text(json.dumps(result, ensure_ascii=False, indent=0))
total = sum(v["size"] for v in result.values())
print(f"\nTotal raw: {total/1024:.1f} KB")
print(f"Total b64: {sum(len(v['data']) for v in result.values())/1024:.1f} KB")
print(f"Wrote: {OUT}")
```

保存到 `/Users/jarvis/Documents/VideoToDoc-skills/scripts/build_embedded.py`

- [ ] **步骤 2: 运行构建脚本**

```bash
cd /Users/jarvis/Documents/VideoToDoc-skills
python3 scripts/build_embedded.py
```

预期输出: 4 行"xxx bytes -> xxx b64 chars",最后写 `docs/trae-competition/assets/embedded.json`,总 b64 大小约 1.6MB

- [ ] **步骤 3: 验证生成**

```bash
ls -la /Users/jarvis/Documents/VideoToDoc-skills/docs/trae-competition/assets/embedded.json
python3 -c "import json; d=json.load(open('/Users/jarvis/Documents/VideoToDoc-skills/docs/trae-competition/assets/embedded.json')); print('keys:', list(d.keys()))"
```

预期: 4 个键 (slide-1, slide-2, slide-3, mindmap),文件大小约 1.6MB

- [ ] **步骤 4: Commit**

```bash
git add scripts/build_embedded.py docs/trae-competition/assets/embedded.json
git commit -m "feat(trae-comp): generate base64 embedded.json from sample assets"
```

---

### 任务 4: 写 index.html 骨架 + CSS 变量系统

**文件:**
- 创建: `docs/trae-competition/index.html`(占位 HTML,只有 `<head>` + `<style>` 块 + 空 `<body>`)

- [ ] **步骤 1: 创建骨架文件**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>VideoToDoc · 视频一键变图文讲义</title>
<meta name="description" content="把课程、讲座、培训视频一键转成图文讲义。TRAE AI 创造力大赛报名作品。">
<style>
:root{
  --pink:#FB7299;--blue:#00AEEC;--green:#00B894;
  --bg:#FFFFFF;--surface:#F4F5F7;--code-bg:#F4F5F7;
  --text:#18191C;--muted:#61666D;--hint:#9499A0;
  --border:#E3E5E7;--border-strong:#DEE0E3;
  --r-sm:4px;--r-md:6px;--r-lg:8px;--r-xl:12px;
  --s-1:4px;--s-2:8px;--s-3:12px;--s-4:18px;--s-5:24px;--s-6:32px;--s-7:48px;--s-8:64px;
  --font:"-apple-system","PingFang SC","Microsoft YaHei",sans-serif;
  --mono:"SF Mono",Menlo,monospace;
  --maxw:920px;
}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{font-family:var(--font);color:var(--text);background:var(--surface);line-height:1.6;-webkit-font-smoothing:antialiased}
img{max-width:100%;display:block}
code,pre{font-family:var(--mono)}
a{color:inherit;text-decoration:none}
button{font:inherit;cursor:pointer;border:0;background:transparent}
@media(prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important;scroll-behavior:auto!important}}
</style>
</head>
<body>
<!-- 主体见后续任务 -->
</body>
</html>
```

保存到 `/Users/jarvis/Documents/VideoToDoc-skills/docs/trae-competition/index.html`

- [ ] **步骤 2: 浏览器打开验证**

```bash
open /Users/jarvis/Documents/VideoToDoc-skills/docs/trae-competition/index.html
```

预期: 浏览器打开,显示空白白底页面(只有 body 注释)。检查控制台无错误。

- [ ] **步骤 3: Commit**

```bash
git add docs/trae-competition/index.html
git commit -m "feat(trae-comp): HTML skeleton + CSS variable design system"
```

---

### 任务 5: 实现 §1 Hero 段

**文件:**
- 修改: `docs/trae-competition/index.html`

- [ ] **步骤 1: 在 `<body>` 中插入 Hero HTML**

在 `<!-- 主体见后续任务 -->` 替换为:

```html
<section class="hero" id="hero">
  <span class="tag">🎓 学习工作赛道 · 创意提案</span>
  <h1 class="h1"><em>VideoToDoc</em></h1>
  <p class="sub">把课程、讲座、培训视频,一键变成图文讲义</p>
  <p class="kicker">自动转录 · 截图去重 · 图文对齐 · 飞书发布</p>
  <div class="cta-row">
    <a class="btn btn-pri" href="#how">开始使用 →</a>
    <a class="btn btn-ghost" href="https://github.com/jarvislee90s-dot/VideoToDoc-skills" target="_blank" rel="noopener">★ GitHub</a>
  </div>
</section>
```

- [ ] **步骤 2: 在 `<style>` 末尾追加 Hero 样式**

```css
.hero{background:var(--bg);padding:var(--s-8) var(--s-5) var(--s-7);border-bottom:1px solid var(--border);max-width:var(--maxw);margin:0 auto}
.tag{display:inline-block;background:var(--bg);color:var(--pink);font-size:12px;padding:4px 12px;border-radius:var(--r-sm);font-weight:600;border:1.5px solid var(--pink);letter-spacing:.5px}
.h1{font-size:42px;font-weight:800;margin:var(--s-4) 0 var(--s-3);letter-spacing:.5px}
.h1 em{color:var(--pink);font-style:normal}
.sub{color:var(--text);font-size:18px;font-weight:500;margin-bottom:var(--s-2)}
.kicker{color:var(--muted);font-size:13px;letter-spacing:.5px}
.cta-row{margin-top:var(--s-5);display:flex;gap:var(--s-3);flex-wrap:wrap}
.btn{display:inline-block;font-size:14px;font-weight:600;padding:10px 22px;border-radius:var(--r-md);transition:background-color 150ms ease}
.btn-pri{background:var(--pink);color:#fff}
.btn-pri:hover{background:#e85d85}
.btn-ghost{background:var(--bg);color:var(--text);border:1.5px solid var(--text)}
.btn-ghost:hover{background:var(--text);color:var(--bg)}
```

- [ ] **步骤 3: 浏览器验证**

```bash
open /Users/jarvis/Documents/VideoToDoc-skills/docs/trae-competition/index.html
```

预期: 看到白底 Hero,粉色 "VideoToDoc" 强调字,标签粉色描边方块,两个按钮(粉实心 + 黑描边)。检查 hover 效果(粉按钮变深、黑按钮反色)。

- [ ] **步骤 4: Commit**

```bash
git add docs/trae-competition/index.html
git commit -m "feat(trae-comp): §1 Hero with pink accent + dual CTA"
```

---

### 任务 6: 实现 §2 创意介绍 + §3 目标用户 + §4 价值与意义(正文三段)

**文件:**
- 修改: `docs/trae-competition/index.html`

- [ ] **步骤 1: 在 Hero 后插入三段正文 HTML**

```html
<section class="block" id="intro">
  <div class="lab">01 · 创意介绍</div>
  <h2>把视频变成可检索、可分享的图文讲义</h2>
  <div class="grid-3">
    <div class="mini">
      <div class="mini-t">痛点</div>
      <p>培训视频看完一遍就忘,想找回某段内容靠拖进度条;团队培训内容散落在个人收藏夹,无法沉淀。</p>
    </div>
    <div class="mini">
      <div class="mini-t">动机</div>
      <p>把视频自动转成结构化讲义,让 AI 内容可以像文档一样被搜索、引用、协作。</p>
    </div>
    <div class="mini">
      <div class="mini-t">产品形态</div>
      <p>本地 CLI 工具链(三个 Skill) + 飞书云文档输出,免费、Apple Silicon 优化、可在本地完整运行。</p>
    </div>
  </div>
</section>

<section class="block" id="users">
  <div class="lab">02 · 目标用户及痛点</div>
  <h2>给看完长视频想沉淀笔记的人</h2>
  <div class="grid-2">
    <div class="card">
      <div class="card-t">核心用户</div>
      <p>培训学员、课程学生、知识工作者;团队学习负责人、播客主理人、技术布道者。</p>
    </div>
    <div class="card">
      <div class="card-t">使用场景</div>
      <p>看完 1 小时长视频后想沉淀笔记;团队每周分享会要分发可阅读材料;把外部分享沉淀进团队知识库。</p>
    </div>
  </div>
  <div class="callout">
    <b>当前痛点:</b> 手动记笔记效率低(1 小时视频需要 2-3 小时记录);视频无法被全文检索;团队内部知识散落在 IM 截图、个人 Notion 页面,无法共享复用。
  </div>
</section>

<section class="block" id="value">
  <div class="lab">03 · 价值与意义</div>
  <h2>从 1 小时视频到 5 分钟可阅读讲义</h2>
  <div class="grid-3">
    <div class="metric"><div class="m-num" style="color:var(--pink)">5min</div><div class="m-lab">生成完整讲义</div></div>
    <div class="metric"><div class="m-num" style="color:var(--blue)">100%</div><div class="m-lab">本地运行,数据不出机</div></div>
    <div class="metric"><div class="m-num" style="color:var(--green)">3步</div><div class="m-lab">从视频到飞书文档</div></div>
  </div>
  <p class="value-body">把视频转成讲义,把讲义转成可搜索的知识。一次性投入,后续每次看视频都能省下数小时笔记时间,并把个人知识沉淀为团队资产。</p>
</section>
```

- [ ] **步骤 2: 追加对应 CSS**

```css
.block{max-width:var(--maxw);margin:0 auto;padding:var(--s-7) var(--s-5);background:var(--bg);border-bottom:1px solid var(--border)}
.lab{font-size:11px;color:var(--hint);font-weight:600;letter-spacing:1.5px;text-transform:uppercase;margin-bottom:var(--s-3);display:flex;align-items:center;gap:var(--s-2)}
.lab::before{content:"";width:3px;height:14px;background:var(--pink);display:inline-block}
.block h2{font-size:28px;font-weight:800;margin-bottom:var(--s-5);letter-spacing:.3px}
.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:var(--s-3)}
.grid-3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:var(--s-3)}
.card,.mini{background:var(--surface);border:1px solid var(--border);border-radius:var(--r-lg);padding:var(--s-4)}
.card-t,.mini-t{font-weight:700;color:var(--text);font-size:14px;margin-bottom:var(--s-2)}
.card p,.mini p{color:var(--muted);font-size:13.5px;line-height:1.7}
.callout{margin-top:var(--s-4);background:#fff5f8;border:1px solid #fbd1de;border-radius:var(--r-lg);padding:var(--s-3) var(--s-4);color:var(--text);font-size:13.5px;line-height:1.7}
.callout b{color:var(--pink)}
.metric{background:var(--surface);border:1px solid var(--border);border-radius:var(--r-lg);padding:var(--s-4) var(--s-3);text-align:center}
.m-num{font-size:30px;font-weight:800;font-family:var(--mono);letter-spacing:1px}
.m-lab{font-size:11px;color:var(--hint);margin-top:var(--s-1);letter-spacing:.5px}
.value-body{margin-top:var(--s-4);color:var(--muted);font-size:14px;line-height:1.8}
```

- [ ] **步骤 3: 浏览器验证**

预期: Hero 下方依次出现三段正文(创意介绍 / 目标用户 / 价值与意义),三栏网格和双栏网格正常,callout 粉色浅底,三个 metric 数字居中。

- [ ] **步骤 4: Commit**

```bash
git add docs/trae-competition/index.html
git commit -m "feat(trae-comp): §2-§4 three prose blocks (intro/users/value)"
```

---

### 任务 7: 实现 §5 三步工作流(抽屉/手风琴)

**文件:**
- 修改: `docs/trae-competition/index.html`

- [ ] **步骤 1: 插入三步 HTML**

在 §4 后插入:

```html
<section class="block" id="how">
  <div class="lab">04 · 怎么用</div>
  <h2>三步把视频变成可阅读讲义</h2>
  <p class="lead">点击每步展开命令和产物。所有命令路径指向项目内 <code>.agents/skills/</code> 目录。</p>
  <div class="steps">
    <details class="step" open>
      <summary><span class="step-num n1">01</span><span class="step-t">视频转文字</span><span class="step-meta">video-summary</span></summary>
      <div class="step-body">
        <p>URL 或本地视频 → 字幕优先获取 → 失败则 mlx-whisper 本地 ASR fallback → 生成带时间戳的 transcript.json 和纯文本 transcript.txt。</p>
        <pre><code>python3 .agents/skills/video-summary/scripts/process.py "视频URL"</code></pre>
        <p class="note">产物:<code>transcript.json</code> + <code>transcript.txt</code></p>
      </div>
    </details>
    <details class="step">
      <summary><span class="step-num n2">02</span><span class="step-t">截图对齐讲义</span><span class="step-meta">video-to-slides</span></summary>
      <div class="step-body">
        <p>三段式去重(明显重复合并、明显不同保留、不确定 OCR 判定) + 毫秒级图文对齐 + Agent 语义整理。</p>
        <pre><code>python3 .agents/skills/video-to-slides/scripts/process.py video.mp4 \
  --transcript transcript.json</code></pre>
        <p class="note">产物:<code>讲义.md</code> + <code>讲义.docx</code> + <code>思维导图.mmd/.png</code></p>
      </div>
    </details>
    <details class="step">
      <summary><span class="step-num n3">03</span><span class="step-t">发布飞书</span><span class="step-meta">feishu-markdown-publish</span></summary>
      <div class="step-body">
        <p>解析 Markdown 章节,逐页上传飞书云文档(页码 + 图片 + 正文 + 分隔线),末尾追加思维导图。需要本机 lark-cli 登录态。</p>
        <pre><code>python3 .agents/skills/feishu-markdown-publish/scripts/publish.py 讲义.md \
  &lt;space_id_or_wiki_url&gt;</code></pre>
        <p class="note">产物:<b>飞书云文档 URL</b>(可分享、可评论、可搜索)</p>
      </div>
    </details>
  </div>
</section>
```

- [ ] **步骤 2: 追加抽屉 CSS**

```css
.lead{color:var(--muted);font-size:14px;margin-bottom:var(--s-4)}
.lead code{background:var(--code-bg);padding:1px 6px;border-radius:var(--r-sm);font-size:12.5px;color:var(--pink)}
.steps{display:flex;flex-direction:column;gap:var(--s-3)}
.step{background:var(--surface);border:1px solid var(--border);border-radius:var(--r-lg);overflow:hidden;transition:border-color 150ms}
.step[open]{border-color:var(--pink);background:var(--bg)}
.step summary{display:flex;align-items:center;gap:var(--s-3);padding:var(--s-3) var(--s-4);cursor:pointer;list-style:none;user-select:none}
.step summary::-webkit-details-marker{display:none}
.step-num{flex-shrink:0;width:40px;height:40px;border-radius:var(--r-md);display:flex;align-items:center;justify-content:center;font-size:15px;font-weight:700;color:#fff;font-family:var(--mono)}
.n1{background:var(--pink)}
.n2{background:var(--blue)}
.n3{background:var(--green)}
.step-t{font-size:15px;font-weight:700;color:var(--text);flex:1}
.step-meta{font-size:11px;color:var(--hint);font-family:var(--mono);letter-spacing:.5px}
.step[open] .step-t{color:var(--pink)}
.step-body{padding:0 var(--s-4) var(--s-4) 64px}
.step-body p{color:var(--muted);font-size:13.5px;line-height:1.7;margin-bottom:var(--s-2)}
.step-body pre{background:var(--code-bg);border-radius:var(--r-md);padding:var(--s-3);overflow-x:auto;margin-bottom:var(--s-2)}
.step-body pre code{color:var(--pink);font-size:12.5px;line-height:1.6}
.note{font-size:12.5px;color:var(--muted)}
.note code,.note b{background:var(--code-bg);padding:1px 6px;border-radius:var(--r-sm);font-size:12px;color:var(--pink)}
.note b{color:var(--green);background:#e6faf3}
```

- [ ] **步骤 3: 浏览器验证**

预期: 三步手风琴。第 1 步默认展开(带粉色描边 + 白底),点第 2 步切换展开/折叠,折叠时变回灰底,展开时变粉描边 + 白底,序号 01/02/03 颜色不变(粉/蓝/绿),命令块可滚动。

- [ ] **步骤 4: Commit**

```bash
git add docs/trae-competition/index.html
git commit -m "feat(trae-comp): §5 three-step workflow as drawer/accordion"
```

---

### 任务 8: 实现 §6 看效果(嵌入 base64 样例)

**文件:**
- 修改: `docs/trae-competition/index.html`

- [ ] **步骤 1: 读 embedded.json 备用**

```bash
python3 -c "
import json
d = json.load(open('/Users/jarvis/Documents/VideoToDoc-skills/docs/trae-competition/assets/embedded.json'))
for k,v in d.items(): print(k, v['alt'], len(v['data']))
"
```

预期: 4 行输出,每行: key + alt + b64 字符串长度

- [ ] **步骤 2: 注入 embedded.json 数据到 index.html**

将 `embedded.json` 内容内联进 index.html(用 Python 脚本一次性生成,避免手抄):

```bash
python3 <<'PY'
import json, re
p_html = '/Users/jarvis/Documents/VideoToDoc-skills/docs/trae-competition/index.html'
p_json = '/Users/jarvis/Documents/VideoToDoc-skills/docs/trae-competition/assets/embedded.json'
html = open(p_html, encoding='utf-8').read()
data = json.load(open(p_json, encoding='utf-8'))
inject = '<script>window.__EMBEDDED__ = ' + json.dumps(data, ensure_ascii=False) + ';</script>'
html = html.replace('</head>', inject + '\n</head>')
open(p_html, 'w', encoding='utf-8').write(html)
print('injected', len(inject), 'chars')
PY
```

预期: 输出 `injected XXXXX chars`,大小约 1.6MB 的 JSON 字符串被嵌入 `<head>`。

- [ ] **步骤 3: 在 §5 后插入 §6 HTML**

```html
<section class="block" id="showcase">
  <div class="lab">05 · 看效果</div>
  <h2>真实跑批产物:AI 日报 0611</h2>
  <p class="lead">下面是 VideoToDoc 在一个真实 AI 日报视频(Anthropic 认错 + OpenAI 降价 + MiniMax M3 开源)上跑出的产物样例。</p>
  <div class="gallery">
    <figure class="shot">
      <img data-img="slide-1" alt="讲义截图 1">
      <figcaption>第 1 页 · Anthropic 撤回静默降智</figcaption>
    </figure>
    <figure class="shot">
      <img data-img="slide-2" alt="讲义截图 2">
      <figcaption>第 4 页 · OpenAI 大幅降价</figcaption>
    </figure>
    <figure class="shot">
      <img data-img="slide-3" alt="讲义截图 3">
      <figcaption>第 7 页 · MiniMax M3 开源</figcaption>
    </figure>
  </div>
  <div class="mindmap-wrap">
    <h3>思维导图</h3>
    <img data-img="mindmap" alt="思维导图" class="mindmap-img">
  </div>
  <div class="text-excerpt">
    <h3>讲义节选:从口播到书面</h3>
    <div class="exc-cols">
      <div class="exc">
        <div class="exc-tag raw">原始转录</div>
        <p>"嗯那个今天我们来聊一下就是啊最近这个 AI 圈的一些大事件 首先是 Anthropic 这个事 嗯 之前有报道说他们静默降智..."</p>
      </div>
      <div class="exc-arr">→</div>
      <div class="exc">
        <div class="exc-tag done">整理后</div>
        <p><b>Anthropic 撤回静默降智,转为可见机制</b><br>Anthropic 撤回了对 Claude 5 系列模型"对大模型开发相关请求进行静默破坏"的策略,承认此前不透明的做法是错误的权衡。从本周起,相关防护机制转为可见:系统会明确拒绝这些请求,或回退至较弱的 OP4.8 模型。</p>
      </div>
    </div>
  </div>
</section>
```

- [ ] **步骤 4: 追加 §6 CSS**

```css
.gallery{display:grid;grid-template-columns:1fr 1fr 1fr;gap:var(--s-3);margin-top:var(--s-4)}
.shot{background:var(--surface);border:1px solid var(--border);border-radius:var(--r-lg);padding:var(--s-3);margin:0}
.shot img{border-radius:var(--r-md);margin-bottom:var(--s-2);width:100%}
.shot figcaption{font-size:12px;color:var(--muted);text-align:center}
.mindmap-wrap{margin-top:var(--s-5);background:var(--surface);border:1px solid var(--border);border-radius:var(--r-lg);padding:var(--s-4)}
.mindmap-wrap h3{font-size:14px;color:var(--text);margin-bottom:var(--s-3)}
.mindmap-img{max-width:100%;border-radius:var(--r-md);background:#fff}
.text-excerpt{margin-top:var(--s-5)}
.text-excerpt h3{font-size:16px;color:var(--text);margin-bottom:var(--s-3)}
.exc-cols{display:grid;grid-template-columns:1fr 32px 1fr;gap:var(--s-3);align-items:stretch}
.exc{background:var(--surface);border:1px solid var(--border);border-radius:var(--r-lg);padding:var(--s-3) var(--s-4)}
.exc p{font-size:12.5px;color:var(--muted);line-height:1.7}
.exc p b{color:var(--text);font-size:13.5px;display:block;margin-bottom:var(--s-1)}
.exc-tag{display:inline-block;font-size:10.5px;padding:2px 8px;border-radius:var(--r-sm);font-weight:700;letter-spacing:.5px;margin-bottom:var(--s-2)}
.exc-tag.raw{background:#fff5f8;color:var(--pink);border:1px solid #fbd1de}
.exc-tag.done{background:#e6faf3;color:var(--green);border:1px solid #b9ead4}
.exc-arr{display:flex;align-items:center;justify-content:center;color:var(--hint);font-size:20px}
```

- [ ] **步骤 5: 追加 JS 把 data-img 替换为 base64 data URI**

在 `</body>` 之前插入:

```html
<script>
(function(){
  var em = window.__EMBEDDED__ || {};
  document.querySelectorAll('img[data-img]').forEach(function(img){
    var key = img.getAttribute('data-img');
    var item = em[key];
    if (item) { img.src = item.data; img.alt = item.alt; img.removeAttribute('data-img'); }
  });
})();
</script>
```

- [ ] **步骤 6: 浏览器验证**

预期: §6 出现三张讲义截图(从 RUN2 真实产物)+ 思维导图 + 讲义节选(原始 vs 整理后)。图片正常显示,文件大小 ~ 1.6MB。

- [ ] **步骤 7: 检查文件大小**

```bash
du -h /Users/jarvis/Documents/VideoToDoc-skills/docs/trae-competition/index.html
```

预期: 约 1.8-2.2MB(< 20MB 大赛限制,远低于目标)

- [ ] **步骤 8: Commit**

```bash
git add docs/trae-competition/index.html
git commit -m "feat(trae-comp): §6 showcase with embedded base64 sample images"
```

---

### 任务 9: 实现 §7 开始用 + 整体收尾

**文件:**
- 修改: `docs/trae-competition/index.html`

- [ ] **步骤 1: 在 §6 后插入 §7**

```html
<section class="block end" id="start">
  <div class="lab">06 · 开始用</div>
  <h2>三步把任意视频变成团队知识</h2>
  <p class="lead">项目已开源,clone 下来跑三条命令即可。MIT 协议,免费,本地运行。</p>
  <div class="end-cta">
    <a class="btn btn-pri btn-lg" href="https://github.com/jarvislee90s-dot/VideoToDoc-skills" target="_blank" rel="noopener">★ GitHub: jarvislee90s-dot/VideoToDoc-skills</a>
  </div>
  <div class="links">
    <a class="link-card" href="https://github.com/jarvislee90s-dot/VideoToDoc-skills/tree/main/.agents/skills/video-summary" target="_blank" rel="noopener">
      <span class="link-t">video-summary</span>
      <span class="link-d">视频 → 字幕 / ASR → transcript</span>
    </a>
    <a class="link-card" href="https://github.com/jarvislee90s-dot/VideoToDoc-skills/tree/main/.agents/skills/video-to-slides" target="_blank" rel="noopener">
      <span class="link-t">video-to-slides</span>
      <span class="link-d">视频 + transcript → 截图对齐讲义</span>
    </a>
    <a class="link-card" href="https://github.com/jarvislee90s-dot/VideoToDoc-skills/tree/main/.agents/skills/feishu-markdown-publish" target="_blank" rel="noopener">
      <span class="link-t">feishu-markdown-publish</span>
      <span class="link-d">Markdown → 飞书云文档</span>
    </a>
  </div>
  <footer class="foot">
    <p>报名赛道 · 学习工作 | GitHub · jarvislee90s-dot/VideoToDoc-skills | TRAE AI 创造力大赛 2026</p>
  </footer>
</section>
```

- [ ] **步骤 2: 追加 §7 CSS**

```css
.end{text-align:center}
.end h2{margin-bottom:var(--s-3)}
.end-cta{margin:var(--s-5) 0 var(--s-6)}
.btn-lg{padding:14px 32px;font-size:15px}
.links{display:grid;grid-template-columns:1fr 1fr 1fr;gap:var(--s-3);margin-top:var(--s-4);text-align:left}
.link-card{display:block;background:var(--surface);border:1px solid var(--border);border-radius:var(--r-lg);padding:var(--s-3) var(--s-4);transition:border-color 150ms}
.link-card:hover{border-color:var(--pink)}
.link-t{display:block;font-weight:700;color:var(--text);font-size:14px;margin-bottom:var(--s-1);font-family:var(--mono)}
.link-d{display:block;font-size:12.5px;color:var(--muted)}
.foot{margin-top:var(--s-7);padding-top:var(--s-4);border-top:1px solid var(--border)}
.foot p{font-size:11.5px;color:var(--hint);letter-spacing:.5px}
```

- [ ] **步骤 3: 浏览器验证整体**

```bash
open /Users/jarvis/Documents/VideoToDoc-skills/docs/trae-competition/index.html
```

预期: 7 段叙事流完整。点击 GitHub/三个 Skill 链接都能打开新标签。

- [ ] **步骤 4: Commit**

```bash
git add docs/trae-competition/index.html
git commit -m "feat(trae-comp): §7 final CTA + links + footer"
```

---

### 任务 10: 写报名帖 .md(配套帖子正文)

**文件:**
- 创建: `docs/trae-competition/报名帖.md`

- [ ] **步骤 1: 按大赛模板写正文**

四部分(创意名称+介绍 / 目标用户及痛点 / 价值与意义)+ 附录(本 HTML 说明)。

```markdown
# VideoToDoc · 学习工作赛道

## 创意名称 + 创意介绍

**VideoToDoc** 是一个本地运行的视频转图文讲义工具链,把课程、讲座、培训视频一键变成可阅读、可检索、可分享的结构化讲义。

想解决什么问题:长视频看完一遍就忘,想找回某段内容只能拖进度条;团队培训内容散落在个人收藏夹,无法沉淀复用;手动做笔记 1 小时视频需要 2-3 小时,效率极低。

为什么会想到做这个:自己每次看 AI/技术分享视频都要花数倍时间记笔记,事后又找不到内容,觉得应该有工具把这件事自动化。

大概是什么产品:本地 CLI 工具链(三个 Skill) + 飞书云文档输出。Apple Silicon 优化,免费,数据不出本地。

## 目标用户及痛点

**面向哪些用户:** 培训学员、课程学生、知识工作者;团队学习负责人、播客主理人、技术布道者。

**在什么场景下使用:** 看完 1 小时长视频后想沉淀笔记;团队每周分享会要分发可阅读材料;把外部分享沉淀进团队知识库。

**当前痛点:** 手动记笔记效率低;视频无法被全文检索;团队内部知识散落在 IM 截图、个人 Notion 页面,无法共享复用。

## 价值与意义

- **效率提升:** 从 1 小时视频到 5 分钟生成完整图文讲义,效率提升 10 倍以上
- **知识沉淀:** 讲义入库可搜索、可评论、可分享,个人笔记变团队资产
- **落地成本:** 本地运行、免费、Apple Silicon 优化、MIT 协议开源

## 必须附带:创意产物 HTML

附件是我做的单文件 HTML 报名作品,既是一份完整的创意展示,也是一份动态使用说明书——打开 HTML 可以照着命令把 VideoToDoc 用起来。

**本地预览:**

\`\`\`bash
open docs/trae-competition/index.html
\`\`\`

**GitHub:** <https://github.com/jarvislee90s-dot/VideoToDoc-skills>
```

保存到 `/Users/jarvis/Documents/VideoToDoc-skills/docs/trae-competition/报名帖.md`

- [ ] **步骤 2: 字数与内容核验**

```bash
wc -m /Users/jarvis/Documents/VideoToDoc-skills/docs/trae-competition/报名帖.md
echo "---"
grep -c "^## " /Users/jarvis/Documents/VideoToDoc-skills/docs/trae-competition/报名帖.md
```

预期: 字符数 > 600,`##` 标题 ≥ 4 个(创意/用户/价值/HTML)

- [ ] **步骤 3: Commit**

```bash
git add docs/trae-competition/报名帖.md
git commit -m "docs(trae-comp): add registration post markdown"
```

---

### 任务 11: 整体验证 + 产物清单

**文件:**
- (无新文件,只验证)

- [ ] **步骤 1: 文件清单**

```bash
ls -la /Users/jarvis/Documents/VideoToDoc-skills/docs/trae-competition/
du -h /Users/jarvis/Documents/VideoToDoc-skills/docs/trae-competition/index.html
du -h /Users/jarvis/Documents/VideoToDoc-skills/docs/trae-competition/报名帖.md
```

预期: 包含 `index.html`(1.8-2.2MB)、`报名帖.md`(< 10KB)、`assets/`(含 4 张 PNG + embedded.json)

- [ ] **步骤 2: HTML 7 段叙事流自检**

```bash
grep -c "^<section" /Users/jarvis/Documents/VideoToDoc-skills/docs/trae-competition/index.html
grep "id=" /Users/jarvis/Documents/VideoToDoc-skills/docs/trae-competition/index.html | grep -E 'id="(hero|intro|users|value|how|showcase|start)"'
```

预期: `<section` 出现 7 次,且 id 包含 `hero / intro / users / value / how / showcase / start`

- [ ] **步骤 3: 禁渐变自检**

```bash
grep -n "linear-gradient\|radial-gradient" /Users/jarvis/Documents/VideoToDoc-skills/docs/trae-competition/index.html && echo "FAIL: 渐变存在" || echo "OK: 无渐变"
```

预期: `OK: 无渐变`

- [ ] **步骤 4: 浏览器最终验收**

```bash
open /Users/jarvis/Documents/VideoToDoc-skills/docs/trae-competition/index.html
```

完整跑一遍: Hero → 创意 → 用户 → 价值 → 三步(默认 01 展开,点开 02/03 切换)→ 看效果(三张图 + 思维导图 + 节选)→ 开始用 → GitHub 链接。验收清单:

- [ ] Hero 渲染正确,粉强调字 + 双 CTA
- [ ] 三段正文网格布局正常
- [ ] 三步抽屉切换正常(默认 01 展开,点击 02/03 切换)
- [ ] §6 三张样例图、思维导图、节选都显示
- [ ] §7 主 CTA + 三个 Skill 链接可点
- [ ] 控制台无 error/warning
- [ ] 页面整体无任何渐变(纯色块)
- [ ] 文字对比清晰,无白底白字

- [ ] **步骤 5: 最终 commit + tag**

```bash
git add docs/trae-competition/
git commit -m "feat(trae-comp): complete registration HTML + post for TRAE AI competition"
git tag trae-comp-v1
```

---

## 自检结果

**1. 规格覆盖度:**
- §1 Hero → 任务 5 ✓
- §2 创意介绍 → 任务 6 ✓
- §3 目标用户 → 任务 6 ✓
- §4 价值与意义 → 任务 6 ✓
- §5 三步流程(抽屉) → 任务 7 ✓
- §6 看效果(真实产物 base64) → 任务 8 ✓
- §7 开始用 CTA → 任务 9 ✓
- 报名帖 .md → 任务 10 ✓
- 验证 + 清单 → 任务 11 ✓

**2. 占位符扫描:** 全部步骤含实际代码,无 TODO / "类似任务 N" / "添加适当的错误处理"。

**3. 类型一致性:** `step-num` / `n1` / `n2` / `n3` / `data-img` / `__EMBEDDED__` 在所有任务中命名一致。
