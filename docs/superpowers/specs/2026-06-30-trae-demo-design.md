# VideoToDoc 初赛 Demo 设计文档

## 1. 背景与目标

### 1.1 参赛要求
- **赛事**：TRAE AI 创造力大赛初赛
- **提交形式**：在初赛专区发布 Demo 作品帖
- **Demo 要求**：可交互、能体验，必须附带体验地址（在线链接 / HTML ZIP / 演示视频）
- **评审维度**：创意价值、技术实现、用户体验、展示表达
- **必备内容**：开发关键步骤截图 ≥3 张、关键任务 Session ID ≥3 个

### 1.2 项目现状
- 已报名赛道：**学习工作**
- 创意名称：VideoToDoc — 视频一键变图文讲义
- 已有一个 GitHub 开源仓库：`jarvislee90s-dot/VideoToDoc-skills`
- 已有三个本地 Skill：video-summary、video-to-slides、feishu-markdown-publish
- 已有真实跑批产物：`runs/SpaceX上市，背后在玩什么资本游戏_20260630_231231/`

### 1.3 Demo 目标
制作一个单文件 HTML Demo，让评审打开页面即可体验"AI Agent 自主完成视频→讲义→飞书"的完整工作流，同时展示：
1. 这是由 **TRAE Skill** 驱动的 Agent
2. Agent 会读取 SKILL.md、调用脚本、产出文件
3. 每一步产物都是真实可验证的

---

## 2. 方案选择

### 2.1 三个候选方案

| 方案 | 核心 | 优点 | 缺点 | 结论 |
|---|---|---|---|---|
| **A. 全模拟回放** | HTML 内嵌真实跑批数据，按脚本播放 | 零依赖、零故障、单文件可体验、产物可验证 | 不是实时执行 | **采用** |
| B. 半真实混合 | 对话调用真实 LLM，Skill 执行预录 | 交互更"真" | 评审无 API key 则卡死，复杂度高 | 放弃 |
| C. 全真实执行 | 本地起后端服务跑 Python 脚本 | 100% 真实 | 评审无法直接体验 | 放弃 |

### 2.2 选择理由
初赛评审场景下，**稳定性第一**。全模拟回放能保证每位评审打开 HTML 都能看到一致、完整、流畅的体验；预录数据来自真实跑批，足以展示 Agent 编排逻辑与产物价值。

---

## 3. 整体架构

### 3.1 产物形态
- **单文件 HTML**（ZIP 上传至初赛专区，社区限制 20MB）
- 无外部 JS 框架依赖
- CSS 全部内联
- 产物数据通过 **GitHub raw URL** 引用

### 3.2 数据来源
- 原始跑批目录：`runs/SpaceX上市，背后在玩什么资本游戏_20260630_231231/`
- 上传至 GitHub：`demo-assets/spacex/`
- 引用前缀：`https://raw.githubusercontent.com/jarvislee90s-dot/VideoToDoc-skills/main/demo-assets/spacex/`

### 3.3 页面结构（单页长滚动）

1. **Hero 区**：Demo 标题 + 一句话价值 + 预填 SpaceX 视频链接
2. **配置面板**：API Key / Base URL / 模型选择（展示用，不真实调用）
3. **Agent 对话流**：预设用户-Agent 对话，逐条播放
4. **三列节点执行流**：核心可视化区
   - 左列：Agent 操作（读取 SKILL.md、调用决策）
   - 中列：脚本执行（process.py / publish.py 等）
   - 右列：产出文件（Markdown / JSON / PNG / 飞书链接）
5. **产物展示区**：每个 Skill 完成后展开真实产物
6. **页脚**：GitHub 仓库链接、报名帖链接、Session ID 列表

---

## 4. 视觉与交互设计

### 4.1 设计风格
- 沿用报名 HTML 的 **B站浅色设计语言**
- 主色调：粉色 `#FB7299`、蓝色 `#00AEEC`、绿色 `#00B894`
- 背景使用极淡渐变 `#f8f9fc → #fff → #fff → #f8f9fc`
- 卡片圆角、微投影、无渐变图标

### 4.2 三列节点执行流

| 列 | 内容 | 激活色 |
|---|---|---|
| Agent 操作 | 读取 SKILL.md、调用脚本、回归决策 | 粉色 `#FB7299` |
| 脚本执行 | process.py / publish_markdown.py 运行 | 蓝色 `#00AEEC` |
| 产出文件 | Markdown / JSON / PNG / 飞书链接 | 绿色 `#00B894` |

三列之间用垂直虚线分隔，当前激活列带同色极淡背景。

### 4.3 节点状态动画

| 状态 | 视觉表现 |
|---|---|
| 未激活 | 透明度 35%，边框浅灰，无动画 |
| 正在运行 | 边框加粗 + 同色极淡背景 + 轻微呼吸缩放（scale 1.00 → 1.015，800ms 循环） |
| 已完成 | 边框 2px，透明度 100%，右侧 ✓ 标记，背景恢复白色 |

脚本执行节点额外效果：
- 进度条从 0% 动画到目标百分比
- 标题左侧 ⚡ 脉冲圆点
- 运行日志逐行打字机效果

### 4.4 文件使用状态连线

**连线触发时机：**
- 脚本执行时：从输入文件 → 脚本节点
- 脚本产出时：从脚本节点 → 产出文件
- Agent 进入下一步时：从产出文件 → 下一个 Agent 节点

**连线样式：**
- 虚线 2px，颜色与使用方一致
- 传输中虚线流动动画（stroke-dashoffset 循环）
- 两端高亮圆点
- 中央漂浮标签说明关系，如 `transcript.json → 输入`

### 4.5 Agent 对话框

- 位于节点流上方
- 用户消息左对齐灰色背景
- Agent 消息右对齐蓝色/粉色背景
- 文字不可编辑
- 消息按预设脚本 1.2s 间隔逐条出现

---

## 5. 组件清单

| 组件 | 职责 | 数据依赖 |
|---|---|---|
| `Hero` | 标题、预填输入框、开始按钮 | 无 |
| `ConfigPanel` | 展示 API 配置 | 静态文本 |
| `SkillPrompts` | 三个 Skill 提示词折叠面板 | 三个 SKILL.md 摘要 |
| `AgentChat` | 模拟对话流播放 | `chatScript` |
| `NodeFlow` | 三列节点执行流 | `nodeTimeline` |
| `ConnectionLines` | SVG 动态连线 | 节点坐标、当前步骤 |
| `ProgressBar` | 脚本进度条 | 脚本节点状态 |
| `OutputPanel` | 产物 Markdown / 图片 / 飞书卡片 | GitHub raw URLs |
| `SessionIds` | 页脚 Session ID 展示 | 静态文本 |

---

## 6. 数据与产物

### 6.1 原始素材清单

来自 `runs/SpaceX上市，背后在玩什么资本游戏_20260630_231231/`：

- `SpaceX上市，背后在玩什么资本游戏_总结_20260630_231231.md`
- `SpaceX上市，背后在玩什么资本游戏_讲义_20260630_232710.md`
- `SpaceX上市，背后在玩什么资本游戏_讲义_整理版_20260630_232710.md`
- `SpaceX上市，背后在玩什么资本游戏_讲义_紧凑版_20260630_232710.md`
- `SpaceX上市，背后在玩什么资本游戏_思维导图_渲染_20260630_232710.png`
- `transcript.json`
- `selected_slides_audit_0.06_8_15_False/` 中的截图（精选 8-10 张展示）
- `video.mp4`（可选，作为视频来源证明）

### 6.2 GitHub 产物引用

所有产物上传至 `demo-assets/spacex/` 后，HTML 中通过 raw URL 引用：

```
https://raw.githubusercontent.com/jarvislee90s-dot/VideoToDoc-skills/main/demo-assets/spacex/<filename>
```

### 6.3 飞书链接

使用真实飞书文档链接：
```
https://bcniplbzchv5.feishu.cn/docx/VtMldBO8koF4xTxuOQlck9Zfn2e
```

提交前必须确认该文档已设为"互联网可访问"。

---

## 7. 交互流程

1. 页面加载：输入框预填视频链接，配置面板展示，Skill 提示词折叠
2. 用户点击「开始自动运行」
3. Agent 对话框出现第一条消息
4. 第一个 Skill 节点依次激活：
   - Agent 读取 video-summary/SKILL.md
   - 调用 process.py
   - 进度条推进，日志逐行出现
   - 产出 transcript.json、总结.md
   - 虚线从产出文件连向下一个 Agent 节点
5. 第二个 Skill 节点依次激活：
   - Agent 读取 video-to-slides/SKILL.md
   - 调用 process.py
   - 产出讲义.md、思维导图.png、截图
   - 产物展示区展开
6. 第三个 Skill 节点依次激活：
   - Agent 读取 feishu-publish/SKILL.md
   - 调用 publish_markdown.py
   - 产出飞书云文档链接
7. 全部完成，页脚 Session ID 区域高亮

---

## 8. 技术实现

### 8.1 技术栈
- 原生 HTML5 + CSS3 + JavaScript
- 无外部框架、无外部 CSS/JS 依赖
- SVG 用于动态连线
- Markdown 产物通过 marked.js 内联渲染（可选，若体积敏感可预渲染为 HTML）

### 8.2 关键实现点
- 节点激活状态通过切换 CSS class 控制
- 连线使用 SVG `<path>`，根据节点坐标动态计算贝塞尔曲线
- 进度条和日志使用 `setTimeout` 模拟时序
- 产物图片使用 GitHub raw URL 懒加载

### 8.3 文件体积控制
- HTML 主体仅包含结构、样式、脚本和数据映射
- 所有图片/文档产物通过 URL 引用，不 base64 内联
- 目标 HTML 体积：< 500KB
- ZIP 体积：< 5MB

---

## 9. 错误处理

| 场景 | 处理 |
|---|---|
| GitHub raw 图片加载失败 | 显示占位图，提示"产物文件可在 GitHub 仓库查看" |
| 飞书文档不可访问 | 保留链接，卡片标注"需登录飞书查看" |
| 用户点击未激活节点 | 无响应或提示"请等待当前步骤完成" |
| 浏览器禁用 JS | 显示静态降级内容：流程图 + 产物链接列表 |

---

## 10. 测试策略

| 测试项 | 方法 |
|---|---|
| HTML 本地可打开 | `open demo.html` 目测 |
| ZIP 小于 20MB | 压缩后检查 |
| GitHub raw URL 可访问 | `curl -I` 逐个检查 200 |
| 飞书文档公开可访问 | 无痕浏览器打开验证 |
| 动画流畅度 | Chrome / Safari 完整运行回放 |
| 移动端布局 | DevTools 模拟手机，检查不崩 |

---

## 11. 后续工作

1. 将 SpaceX 跑批目录上传至 GitHub `demo-assets/spacex/`
2. 生成产物 URL 映射表
3. 编写 Demo HTML（单文件）
4. 本地测试动画与产物展示
5. 打包 ZIP 并检查体积
6. 发布初赛 Demo 帖
