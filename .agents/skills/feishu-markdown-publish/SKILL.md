---
name: feishu-markdown-publish
description: "将本地 VideoToDoc Markdown 文档发布到飞书云文档。触发条件：用户要求把 Markdown 发布到飞书；用户说'发布到飞书'、'上传到 Lark'、'飞书文档'；已有 <视频标题>_讲义_整理版_<时间戳>.md 需要发布时。"
---

# feishu-markdown-publish

把本地 Markdown 发布成飞书云文档。这个 Skill 不处理视频、不跑 ASR、不生成 Word；它只接收一个本地 Markdown 文档，以及一个可选的飞书知识库目标。

运行产物写到当前项目的 `runs/_feishu_publish/` 下。Skill 文件夹运行时保持只读。

## 工作流

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

## 输入

- 必填：本地 Markdown 路径（如 `runs/<视频标题>_<时间戳>/<视频标题>_讲义_整理版_<时间戳>.md`）
- 可选：飞书知识库。可以是 `https://.../wiki/space/<space_id>` 形式，也可以直接传 `space_id`；不传则发布到公共文档。
- 可选：标题。默认从 Markdown 第一个 `# 标题` 提取；没有 H1 时用文件名。

## 默认命令

```bash
# 发布到公共文档
python3 skills/feishu-markdown-publish/scripts/publish.py \
  runs/<视频标题>_<时间戳>/<视频标题>_讲义_整理版_<时间戳>.md

# 发布到指定知识库
python3 skills/feishu-markdown-publish/scripts/publish.py \
  runs/<视频标题>_<时间戳>/<视频标题>_讲义_整理版_<时间戳>.md \
  "https://example.feishu.cn/wiki/space/<space_id>"

# 只传 space_id
python3 skills/feishu-markdown-publish/scripts/publish.py \
  runs/<视频标题>_<时间戳>/<视频标题>_讲义_整理版_<时间戳>.md \
  7641581418232957895

# Dry-run 检查
python3 skills/feishu-markdown-publish/scripts/publish.py \
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

如果 Markdown 末尾有 `## 思维导图` 且引用了导图图片，按章节顺序追加导图图片。

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

## 注意事项

1. **必须先登录 lark-cli** - 不要在聊天中粘贴 API key
2. **使用相对路径** - lark-cli 要求 Markdown 文件在项目目录内
3. **图片路径正确** - Markdown 内的图片路径需能正确解析
4. **分隔线保留** - 不要把所有图片集中追加到文末

## 版本兼容性

本 Skill 依赖 `lark-cli` 的文档 API。如果 lark-cli 升级导致接口变更，可能需要同步更新 `publish_markdown.py` 脚本。

已知变更（lark-cli v1 → v2）：
- `docs +create`：`--title` 和 `--markdown` 参数已废弃，改为 `--content` + `--doc-format markdown`
- `docs +update`：`--mode` 参数已废弃，改为 `--command`

如遇发布失败，请先检查 lark-cli 版本：

```bash
lark-cli --version
lark-cli docs +create --help
lark-cli docs +update --help
```
