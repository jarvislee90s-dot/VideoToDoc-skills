# Feishu Markdown Publish Skill

> 将本地 VideoToDoc Markdown 文档发布到飞书云文档

## 功能概览

将 VideoToDoc 生成的 Markdown 文档按图文顺序发布到飞书：

- 📋 **按页分块** - 解析 `### 第 N 页` 结构，每页独立处理
- 🖼️ **图片上传** - 本地图片通过 `lark-cli +media-insert` 上传
- 📚 **知识库支持** - 可指定目标知识库，默认发布到公共文档
- 🔗 **分隔线保留** - 页与页之间自动插入分隔线
- 🧠 **思维导图** - 自动识别并追加导图图片

## 工作流程

```
输入 Markdown（如：<视频标题>_讲义_整理版_<时间戳>.md）
        │
        ▼
┌───────────────────┐
│   检查 lark-cli   │
│   登录状态         │
└─────────┬─────────┘
          │
          ▼
    解析 Markdown
        │
        ▼
┌───────────────────┐
│   提取文档结构     │
│   - 标题           │
│   - 页码小节       │
│   - 图片           │
│   - 思维导图       │
└─────────┬─────────┘
          │
          ▼
    创建飞书文档
        │
        ▼
    逐页发布：
    ┌─────────────┐
    │ 页码标题    │
    │ 图片上传    │
    │ 正文内容    │
    │ 分隔线      │
    └──────┬──────┘
           │
           ▼
    追加思维导图（如有）
           │
           ▼
      飞书文档 URL
```

## 前置条件

1. **lark-cli 已安装并登录**：
   ```bash
   # 检查是否安装
   lark-cli --version
   
   # 如未登录，执行
   lark-cli config init
   lark-cli auth login --recommend
   ```

2. **VideoToDoc 产物** - 已生成 `<视频标题>_讲义_整理版_<时间戳>.md`

## 快速开始

```bash
# 发布到公共文档
python3 scripts/publish_markdown.py \
  runs/<视频标题>_<时间戳>/<视频标题>_讲义_整理版_<时间戳>.md

# 发布到指定知识库
python3 scripts/publish_markdown.py \
  runs/<视频标题>_<时间戳>/<视频标题>_讲义_整理版_<时间戳>.md \
  "https://example.feishu.cn/wiki/space/7641581418232957895"

# 只传 space_id
python3 scripts/publish_markdown.py \
  runs/<视频标题>_<时间戳>/<视频标题>_讲义_整理版_<时间戳>.md \
  7641581418232957895

# Dry-run 检查
python3 scripts/publish_markdown.py \
  runs/<视频标题>_<时间戳>/<视频标题>_讲义_整理版_<时间戳>.md --dry-run
```

## 参数说明

| 参数 | 必填 | 说明 |
|------|------|------|
| `markdown` | ✓ | 本地 Markdown 文件路径 |
| `target` | - | 知识库 URL 或 space_id |
| `--title` | - | 文档标题（默认从 H1 提取） |
| `--identity` | - | `user` 或 `bot`（默认 user） |
| `--dry-run` | - | 只打印命令，不执行 |

## 发布规则

### 页结构解析

每个 `### 第 N 页 · 时间` 小节按固定顺序发布：

```
页码 + 时间标题 → 图片 → 正文 → 分隔线
```

示例：
```
### 第 1 页 · 00:00 - 00:30
![第 1 页](selected_slides/0001.png)
这一页讲解了...

---
```

发布后飞书文档结构：
```
第 1 页 · 00:00 - 00:30  [蓝色页码 + 灰色时间]
[图片居中]
这一页讲解了...
[分隔线]
第 2 页 · ...
```

### 思维导图处理

如果 Markdown 末尾有 `## 思维导图` 章节：

```markdown
## 思维导图

![思维导图](mindmap.png)
```

会自动追加在文档末尾，导图图片居中显示。

## 注意事项

1. **必须先登录 lark-cli** - 不要在聊天中粘贴 API key
2. **使用相对路径** - lark-cli 要求 Markdown 文件在项目目录内
3. **图片路径正确** - Markdown 内的图片路径需能正确解析
4. **分隔线保留** - 不要把所有图片集中追加到文末

## 文件结构

```
feishu-markdown-publish/
├── SKILL.md         # Skill 操作手册（触发条件、工作流、参数）
├── README.md        # 本文件（项目介绍、安装、产物）
├── scripts/
│   ├── publish_markdown.py   # 发布入口脚本
│   └── _project.py  # 项目路径定位
└── assets/
    └── task_flow.png # 整体流程图
```

## 输出目录

发布中间文件写入 `runs/_feishu_publish/<md_name>/`：

```
runs/_feishu_publish/<视频标题>_讲义_整理版_<时间戳>/
├── initial.md        # 初始文档
├── header.md         # 文档头部
├── section_001_title.md
├── section_001_body.md
├── section_001_divider.md
├── section_002_...
├── mindmap_title.md
├── mindmap_body.md
└── assets/           # 上传的图片副本
```

## 相关 Skill

- **video-summary** - 视频转文字摘要
- **video-to-slides** - 视频截图生成图文讲义

## License

MIT License
