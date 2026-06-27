# Task 3 执行报告：子进程调用增加 timeout（A-P0-5）

## 任务概述

为所有子进程调用增加 timeout 机制，防止 ffmpeg、lark-cli、mmdc、tesseract 等外部命令僵死导致整个流程无限挂起。

## 修改文件清单

### 1. `utils.py` — `run_command` 增加 timeout 参数

**位置**: `.agents/skills/video-to-slides/scripts/videotodoc/utils.py:13-45`

**变更内容**:
- 新增 keyword-only 参数 `timeout: float = 120`（默认 120 秒），保持向后兼容
- 将 `timeout` 传递给 `subprocess.run()`
- 新增 `subprocess.TimeoutExpired` 异常捕获，转换为 `VideoToDocError`
- 错误信息包含命令字符串、超时秒数，以及可用的 stdout/stderr 输出

```python
def run_command(
    args: list[str],
    cwd: Path | None = None,
    *,
    timeout: float = 120,
) -> subprocess.CompletedProcess[str]:
```

### 2. `slides.py` — ffmpeg 调用点超时设置

**位置**: `.agents/skills/video-to-slides/scripts/videotodoc/slides.py`

| 函数 | timeout 值 | 说明 |
|------|-----------|------|
| `detect_scene_changes` | 600s | 大视频场景检测可能耗时数分钟 |
| `extract_frame` | 30s | 单帧提取应快速完成 |

### 3. `audio.py` — ffprobe/ffmpeg 调用点超时设置

**位置**: `.agents/skills/video-to-slides/scripts/videotodoc/audio.py`

| 函数 | timeout 值 | 说明 |
|------|-----------|------|
| `probe_duration_ms` (ffprobe) | 30s | 读取视频元数据，操作很快 |
| `extract_audio` (ffmpeg) | 300s | 音频提取，大视频可能需要数分钟 |

### 4. `ocr.py` — tesseract 调用超时设置

**位置**: `.agents/skills/video-to-slides/scripts/videotodoc/ocr.py:29`

| 函数 | timeout 值 | 说明 |
|------|-----------|------|
| `extract_text` (tesseract) | 30s | 单张图片 OCR 应快速完成 |

### 5. `mindmap.py` — mmdc 渲染超时设置

**位置**: `.agents/skills/video-to-slides/scripts/videotodoc/mindmap.py:57-79`

| 函数 | timeout 值 | 说明 |
|------|-----------|------|
| `_run_mmdc` | 120s | Mermaid CLI 渲染，Puppeteer 启动可能较慢 |

为 `_run_mmdc` 中的 `subprocess.run()` 添加了 `timeout=120`，并新增 `subprocess.TimeoutExpired` 异常处理，错误信息格式与 `run_command` 保持一致。

### 6. `feishu-markdown-publish/publish.py` — lark-cli 调用超时设置

**位置**: `.agents/skills/feishu-markdown-publish/scripts/publish.py:179-206`

| 方法 | timeout 值 | 说明 |
|------|-----------|------|
| `Publisher._run` | 60s | lark-cli API 调用，单次请求不应超过 60s |

变更内容:
- `_run` 方法新增 `timeout: float = 60` 参数
- `subprocess.run()` 添加 `timeout=timeout`
- 捕获 `subprocess.TimeoutExpired`，超时自动重试（最多 4 次，退避等待）
- 最终超时仍未成功则抛出 `RuntimeError`

### 7. 新增测试文件

**位置**: `.agents/skills/video-to-slides/scripts/videotodoc/tests/test_run_command_timeout.py`

测试用例:
1. `test_timeout_raises_video_to_doc_error` — 验证超时命令（sleep 10, timeout=1）抛出 VideoToDocError，错误信息包含命令名和超时值
2. `test_normal_command_completes_within_timeout` — 验证正常命令在超时时间内成功完成
3. `test_default_timeout_allows_quick_commands` — 验证默认 timeout（不传参数）不影响快速命令
4. `test_timeout_error_includes_command_info` — 验证超时错误信息包含命令详情

## 超时值设置依据

| 场景 | timeout | 理由 |
|------|---------|------|
| 默认值 | 120s | 通用外部命令合理上限 |
| ffmpeg 场景检测 | 600s | 需要解码整个视频，大文件可能需要 5-10 分钟 |
| ffmpeg 单帧提取 | 30s | 单帧操作通常秒级完成 |
| ffprobe 元数据 | 30s | 只读文件头，极快 |
| ffmpeg 音频提取 | 300s | 需要处理整个音轨 |
| tesseract OCR | 30s | 单张图片处理很快 |
| mmdc 思维导图 | 120s | Puppeteer 启动+渲染可能需要 30-60s |
| lark-cli API | 60s | 网络请求，含重试机制 |

## TDD 流程

1. **先写测试**: 创建 `test_run_command_timeout.py`，3 个测试因 timeout 参数不存在而失败
2. **实现功能**: 修改 `utils.run_command` 添加 timeout 和 TimeoutExpired 处理
3. **测试通过**: 所有 4 个新增测试通过
4. **更新调用点**: 逐一为各调用点添加适当 timeout 值
5. **全量回归**: 77 个测试全部通过（含原 73 个 + 新增 4 个）

## 向后兼容性

- `timeout` 为 keyword-only 参数（`*` 分隔），现有位置参数调用不受影响
- 默认值 120s 对正常命令无影响（不会误杀），仅对真正僵死的进程生效
- `mindmap.py._run_mmdc` 和 `publish.py._run` 为独立 subprocess 调用，分别添加了等效的超时处理

## 测试结果

```
77 passed in 2.36s
```

所有原有测试 + 新增超时测试全部通过，无回归。
