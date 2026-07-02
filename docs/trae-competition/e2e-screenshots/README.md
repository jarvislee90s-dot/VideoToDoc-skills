# Demo 端到端视觉验证报告

## 测试环境

- 浏览器：Playwright Chromium（通过 MCP 驱动）
- 桌面视口：1280 × 900
- 移动视口：iPhone 14 Pro（393 × 852）
- 本地服务：`python3 -m http.server 8765`（`docs/trae-competition`）
- 测试页面：`http://localhost:8765/demo.html`
- 验证时间：2026-07-02

## 截图评价

| 截图 | 状态 | 问题 |
|---|---|---|
| 01-initial.png | 通过 | Hero、配置面板、三个 Skill 折叠面板均正确渲染，chat/nodeFlow/outputs 初始隐藏。 |
| 02-chat-started.png | 通过 | 聊天区域已出现，用户消息与 Agent 消息气泡样式、对齐方式符合设计。 |
| 03-nodeflow-running.png | 通过 | 节点严格按 Agent / 脚本 / 产出三列排布，当前激活节点有边框高亮与呼吸动画。 |
| 04-connection-lines.png | 通过 | 节点全部点亮后，卡片边缘之间的贝塞尔曲线连线已绘制，无穿卡片现象；标签清晰。 |
| 05-outputs.png | 通过 | 产物面板已展示，summary、讲义 Markdown、思维导图、docx、transcript.json、关键截图、飞书云文档均提供可点击链接；GitHub raw 图片已加载。 |
| 06-mobile.png | 通过 | 视口 393 × 852，点击开始后运行至完成，`document.body.scrollWidth` 等于 393px，无水平溢出；节点流、配置网格、截图画廊均正确响应式折叠。 |

## 总体评价

重新设计后的 demo 满足核心验收标准：

- 节点流按 Agent / 脚本 / 产出三列排布。
- 连线为卡片边缘之间的贝塞尔曲线，不穿过卡片。
- Agent 聊天消息在对应节点完成后按 `afterNode` 时序出现。
- OutputPanel 中所有产物均有可点击链接。
- 移动端 393 × 852 无水平溢出。

验证过程中修复了一处遗漏：原 `demo.html` 完成节点流后未调用 `OutputPanel.show()`，导致产物面板始终隐藏。已将 `run` 函数改为 `async`，并在所有节点完成后 `await OutputPanel.show()`。

## 已知问题

1. **飞书云文档链接 404**：`https://bcniplbzchv5.feishu.cn/docx/VtMldBO8koF4xTxuOQlck9Zfn2e` 返回 `HTTP 404`，该链接在页面中存在且可点击，但目标文档当前不可访问。
2. **`validate_demo.py` 偶发 SSL/读取超时**：脚本对部分 `raw.githubusercontent.com` URL 报 `_ssl.c:1112: The handshake operation timed out` 或 `The read operation timed out`。使用 `curl -I` 单独验证这些 URL 均返回 `HTTP/2 200`，确认资源本身可访问，失败为网络/urllib 偶发超时所致。

## 运行命令

```bash
cd docs/trae-competition
python3 -m http.server 8765 &
```

使用 Playwright MCP 工具完成导航、点击、等待、截图、视口调整。
