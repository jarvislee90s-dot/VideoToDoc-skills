# Video-to-Slides Skill

> 视频截图去重 → 图文对齐 → 语义整理 → 目录 → Agent 思维导图 → render_mindmap → Word

## 功能

- 🖼️ **PPT 截图** - 场景切换 + 15秒兜底，三段式去重
- ⏱️ **图文对齐** - 毫秒级时间轴匹配截图与转录
- 📋 **全文目录** - Agent 自动识别章节并标注时间
- ✨ **语义整理** - Agent 将口语化讲稿改写为书面表达
- 🧠 **思维导图** - Mermaid 格式 + PNG 渲染
- 📄 **多格式输出** - 3 份 Markdown + 2 份 Word

## 工作流程

```
输入视频文件
     │
     ▼
┌───────────────────┐
│   前置检查        │
│ 视频/音频/字幕   │
└─────────┬─────────┘
          │
          ▼
    缺少前置产物？
     /          \
   是            否
   /              \
  ▼               ▼
提示运行      截图 + 去重
video-summary   │
          ┌─────┴─────┐
          │ capture    │
          │ 时长密度截图│
          │ + 分段草案  │
          └─────┬─────┘
                │
                ▼
          ┌─────────────┐
          │ review-seg  │
          │ Agent 介入  │
          │ 分段审查    │
          └─────┬───────┘
                │
                ▼
          finalize
          图文对齐 + 讲义MD
          （跨段截图按区间
           切分文本，句末标点
           回溯断句）
                │
                ▼
          ┌─────────────┐
          │ 生成讲义    │
          │ <标题>_讲义 │
          └──────┬──────┘
                 │
                 ▼
        ┌────────────────┐
        │  Agent 目录    │
        │  Agent 语义整理 │
        │  Agent 思维导图 │
        └───────┬────────┘
                │
                ▼
          ┌─────────────┐
          │ <标题>_讲义_整理版 │
          │ <标题>_思维导图    │
          └──────┬──────┘
                 │
                 ▼
        ┌─────────────────┐
        │ finalize.py    │
        │ 恢复图片+渲染导图│
        │ + Word 输出    │
        └────────┬────────┘
                 │
                 ▼
            Word / PNG 输出
         <标题>_讲义.docx
      <标题>_讲义_整理版.docx
       <标题>_思维导图.png
```

## 前置依赖

- **ffmpeg**：截图和音频提取
- **python3** + VideoToDoc 项目 `.venv`
- **mlx-whisper**：ASR 后端（若 transcript.json 需要重新生成）
- **RapidOCR**：截图 OCR 去重
- **mmdc**（mermaid-cli）：思维导图渲染

## 产物

> 注：`.docx` 与 `.png` 由 `render_mindmap.py` 在 Agent 完成整理后生成。

```
runs/<视频标题>_<时间戳>/
├── <视频标题>_讲义_<时间戳>.md              # 原始换行版
├── <视频标题>_讲义_紧凑版_<时间戳>.md       # 紧凑段落版
├── <视频标题>_讲义_整理版_<时间戳>.md       # 书面整理版（Agent 工作文件）
├── <视频标题>_讲义_<时间戳>.docx           # 原文 Word（render_mindmap 生成）
├── <视频标题>_讲义_整理版_<时间戳>.docx     # 整理版 Word（render_mindmap 生成）
├── <视频标题>_思维导图_<时间戳>.mmd         # Mermaid 导图源文件（Agent 编写）
├── <视频标题>_思维导图_<时间戳>.png         # 渲染后的导图（render_mindmap 生成）
├── <视频标题>_质量报告_<时间戳>.md          # 质量报告
└── selected_slides_<模式>_<参数>/          # 最终截图
```

## 快速开始

```bash
# 标准流程（需要已有视频和转录，仅生成 Markdown）
# 注意：video-summary 下载的视频文件名是 <视频标题>.mp4，不是 video.mp4
python3 scripts/process.py "/path/to/<视频标题>.mp4"

# 指定已有转录（推荐：从 video-summary 产物直接引用）
python3 scripts/process.py \
  "runs/<视频标题>_<时间戳>/<视频标题>.mp4" \
  --transcript "runs/<视频标题>_<时间戳>/transcript.json"

# Agent 完成目录、紧凑版、整理版、手写 <视频标题>_思维导图_<时间戳>.mmd 后，
# 跑 finalize.py 统一收尾（恢复图片 + 渲染导图 + 生成 Word）
python3 scripts/finalize.py "runs/<视频标题>_<时间戳>"

# 手工修改思维导图后单独刷新
python3 scripts/render_mindmap.py "runs/<视频标题>_<时间戳>"
```

## 文件结构

```
video-to-slides/
├── SKILL.md               # 操作手册（触发条件、工作流、参数）
├── README.md              # 本文件（项目介绍、安装、产物）
├── scripts/
│   ├── process.py         # capture + finalize 截图对齐主流程
│   ├── finalize.py        # 阶段3收尾 wrapper（恢复图片 + 渲染导图 + Word）
│   ├── render_mindmap.py  # 思维导图渲染（finalize.py 内部调用，也可单独刷新）
│   ├── restore_images.py  # 语义整理后恢复图片（finalize.py 内部调用）
│   ├── _project.py        # 项目路径定位
│   └── tests/             # 文档断言脚本（check_skill_md_5_6 等）
├── reference/            # 阶段 0 合并流程 + Review Agent prompt
│   ├── merge_procedure.md       # 合并碎段完整流程（review ≤ 2 + check_report 闸口）
│   └── review_agent_prompt.md   # Review Agent 双路径 prompt 模板
├── videotodoc/            # 核心包（pipeline/align/slides/mindmap/document + merge 脚本）
│   ├── prepare_merge.py         # 合并段落数据准备 → merge_input.json
│   ├── apply_merge.py           # 应用合并结果 → transcript_merged.json
│   ├── review_merge.py          # 合并质量客观检查 → merge_review_report.json
│   ├── signal_stats.py          # 视频类型信号统计（L3 提示用）
│   └── tests/                   # 单元测试 + check_review_report.py 闸口
└── assets/
    └── task_flow.png
```

## 与其他 Skill 配合

- **前置**：video-summary（获取视频 + 音频 + 字幕）
- **后续**：feishu-markdown-publish（发布到飞书）

## License

MIT
