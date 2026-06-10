# VideoToDoc 编程计划

## 摘要

目标是做一个本地可运行的“课程视频转图文讲义”流水线：输入课程/讲座视频，输出一份可在飞书文档中编辑的图文讲义，包含转录文字、每页 PPT/讲义截图、截图与讲稿的自动对齐，以及最后的可编辑思维导图。

本机现状：仓库目前只有一个测试视频；`ffmpeg/ffprobe` 可用；`lark-cli` 已安装，版本 `1.0.14`；Python 有 `openai`、`python-docx`、`Pillow`，暂未安装 Whisper/OpenCV/OCR 依赖。

## 技术选择

- 转录后端设计成可插拔，第一版推荐优先接 `Qwen3-ASR-Flash-Filetrans` 或同类 DashScope 文件转写接口，原因是更适合长音频、中文课程和异步处理；同时预留 `faster-whisper large-v3` 本地后端。
- 不把 WhisperX 作为第一版主转录后端，而是作为“需要更细时间戳/说话人分离”时的增强模块；WhisperX 的核心价值是 VAD、强制对齐、词级时间戳和 diarization。
- 截图检测第一版采用稳健启发式：定时抽帧、计算帧差、识别稳定区间、在页面切换前保存该页最后稳定画面，并做感知哈希去重。
- 输出第一版以飞书文档为主：先生成结构化 Markdown/XML 中间文档，再通过 `lark-cli docs +create --api-version v2 --doc-format markdown/xml` 创建飞书文档；保留本地 Markdown 和图片目录作为可追溯产物。
- 思维导图第一版用 Mermaid `mindmap` 生成，附在文档最后，保证可编辑；后续再扩展为飞书白板或图片版。

参考依据：`lark-cli` 官方仓库支持 Docs、Drive、Sheets 等域和 `docs +create`；本机也已装 `lark-cli`。Qwen3-ASR 的官方/阿里云文档显示有 DashScope 长音频/文件转写方向；FunASR 提供 ASR、VAD、标点、说话人相关能力；faster-whisper 是基于 CTranslate2 的 Whisper 高速实现；WhisperX 论文/项目定位是长音频词级时间戳与强制对齐。  
来源：[larksuite/cli](https://github.com/larksuite/cli)、[Alibaba Qwen-ASR API](https://www.alibabacloud.com/help/en/model-studio/qwen-asr-api-reference)、[SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper)、[WhisperX paper](https://arxiv.org/abs/2303.00747)、[FunASR paper](https://arxiv.org/abs/2305.11013)、[OpenAI Whisper prompting guide](https://cookbook.openai.com/examples/whisper_prompting_guide)

## 核心实现

- 建立 CLI 入口，例如 `videotodoc process Videos/xxx.mp4 --out runs/xxx --asr qwen --publish feishu`，统一生成 `audio.wav`、`transcript.json`、`slides.json`、`sections.json`、图片和最终文档。
- 音频阶段：用 `ffmpeg` 抽取 16k/mono WAV；ASR 输出必须包含分段文本、开始/结束时间、置信度或原始响应；提示词模板内置课程场景、中文讲解、数学符号、英文术语、专有名词热词。
- 截图阶段：按 1-2 fps 抽帧；对相邻帧计算结构相似度/直方图差异；将长时间稳定画面聚合为一页；每页保存“切换前最后稳定帧”；用图片 hash 去重，输出页码、截图路径、出现时间区间。
- 对齐阶段：根据每页截图的时间区间匹配转录片段；如果讲述跨多页，则允许相邻页共享同一章节段落；初版用时间轴规则，后续可加 OCR/多模态摘要判断章节归属。
- 文档阶段：每页结构为标题、截图、对应讲稿、可选摘要；最后追加 Mermaid 思维导图代码块；通过 `lark-cli` 创建飞书文档，并输出飞书文档 URL。
- 安全与可维护性：所有中间结果保存在 `runs/<video_slug>/`，重复运行可复用缓存；不批量删除文件或目录；配置放在 `config.yaml` 或 `.env`，API key 不写入仓库。

## 提示词与配置

- ASR prompt 第一版内置：
  ```text
  这是一个课程/讲座录音，主要为中文讲解，可能包含数学公式、金融术语、英文专业术语和软件名。
  请准确保留英文术语原拼写，不要翻译，例如 API、Python、GitHub。
  数学符号和表达式尽量使用标准格式，例如 +、-、×、÷、=、≠、≈、≤、≥、∑、∫、∂、Δ、α、β、γ。
  请补全合理标点，避免无根据扩写；听不清处标记为 [听不清]。
  ```
- 配置项包括：ASR 后端、语言、热词表、抽帧 fps、最小稳定时长、帧差阈值、去重阈值、飞书输出目录/父节点、是否生成本地 docx 备份。
- 对你列的模型表不直接硬编码速度/准确率结论，因为实际速度取决于 GPU、量化方式、音频质量和 batch 设置；计划里会做一套基准脚本，用同一测试视频输出耗时、分段质量和人工抽查结果。

## 测试计划

- 用当前 17 分钟示例视频做端到端验收：能抽音频、完成转录、提取非重复截图、生成章节对齐、创建飞书文档。
- 单元测试覆盖：音频命令生成、ASR 响应标准化、截图稳定区间合并、图片去重、转录片段与页面时间区间匹配。
- 质量验收：截图页数无明显重复/漏页；动态 PPT 优先保留信息最完整的末态；讲稿不出现大段幻觉扩写；飞书文档中图片、正文、Mermaid 代码块可编辑。
- 失败场景：无音轨视频、长时间黑屏/摄像头画面、PPT 中嵌入视频、ASR API 失败、飞书未登录或权限不足时，都给出明确错误和可恢复的中间产物。

## 假设

- 第一版以飞书文档作为主输出，本地 Markdown 作为备份与调试产物。
- 第一版截图检测先不用 OCR/多模态模型，等启发式方案跑通后再增强。
- 第一版优先实现 Qwen/DashScope 文件转写 + 本地 faster-whisper 备用；WhisperX、FunASR、SenseVoice 作为后续可插拔后端。
- 飞书发布依赖已有 `lark-cli` 授权；如未授权，先用 `lark-cli auth login --recommend` 完成登录和权限授予。
