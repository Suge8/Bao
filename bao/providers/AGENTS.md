# bao/providers/ — LLM Provider 适配层

## 🔴 最高优先设计原则（必须遵守）

- 先设计单一路径，再实现；禁止事后叠加控制修补竞态。
- 不增加状态机/定时器/分支前，先删除重复入口，保证一个事实源和一个触发点。
- 优先消除中间态可见性（避免“先到顶部再回底部”），不要靠补丁式回滚逻辑。
- 稳定性修复必须做“减控制审查”：能删则删，保留最小可用控制面。

4 类 Provider 覆盖主流模型。延迟加载，缺依赖不崩。

## STRUCTURE

| 文件 | 职责 |
|------|------|
| `base.py` | Provider 抽象基类 + `ToolCallRequest` 统一 tool-call 结构与 `to_openai_tool_call()` 序列化出口；`normalize_tool_calls()` 负责保留 `raw_arguments` / `argument_parse_error`，解析失败不再静默退化为“空参数但成功” |
| `registry.py` | Provider 注册与路由（按模型前缀自动匹配） |
| `openai_provider.py` | OpenAI 兼容端点（OpenAI/OpenRouter/DeepSeek/Groq/Ollama 等）+ Responses/Completions 自动探测切换（含“system 似乎被忽略”时降级 completions 并缓存）+ Responses SSE 增量流式解析（兼容无 trailing blank 收口）+ 复用 `responses_compat.py` 的 shared tool-call 组装与 `call_id` 归一化 + `_sanitize_messages` 中截图延迟 flush（`_image` → `image_url` user message） |
| `openai_codex_provider.py` | OpenAI Codex OAuth Responses Provider（`openai-codex/*` / `openai_codex/*` 路由）+ SSE 流式解析 + 复用 `responses_compat.py` 的 shared tool-call 组装与 `call_id` 归一化 + `_image` 延迟 flush + progress callback 中断语义对齐 |
| `anthropic_provider.py` | Anthropic Claude 全系列 + tool_result 内原生 image block（`_image` → `source.data` base64）+ data URL 解析防御（`partition(",")` 后空 `b64_data` 跳过，防止畸形 URL 发送空数据） |
| `gemini_provider.py` | Google Gemini 全系列 + `_convert_messages` 中截图延迟 flush（`_image` → `inline_data` Blob user Content）+ 用户图片 `image_url` data URL 解析（要求 `;base64,` 标记 + `b64decode` 异常防御，与 Anthropic 对齐）+ `asyncio.CancelledError` / `ProgressCallbackError` / `StreamInterruptedError` 异常分层处理（与 OpenAI/Anthropic 对齐） |
| `responses_compat.py` | OpenAI Responses API 兼容层（bao 独有）+ `convert_messages_to_responses`（支持 system content blocks，兼容 prompt caching）+ shared `call_id` 归一化 / internal tool id 构造 / streaming tool-call 组装 + 截图延迟 flush（`_image` → `input_image` user message） |
| `api_mode_cache.py` | API 模式自动探测 + 磁盘缓存（bao 独有） |
| `retry.py` | Provider 通用重试辅助（异常分类、Retry-After、progress reset、`run_with_retries()` 单一路径重试壳） + `StreamInterruptedError`（继承 `ProgressCallbackError`，流式中断专用异常） |
| `transcription.py` | 语音转文字 |

## WHERE TO LOOK

| 任务 | 位置 |
|------|------|
| 新增 Provider | `base.py` 继承 → `registry.py` 注册 |
| 修改模型路由 | `registry.py` — 前缀匹配逻辑 |
| 修改 API 模式探测 | `api_mode_cache.py`（auto/responses/completions） |
| 调试 Responses API | `responses_compat.py` |
| 调整 Provider 重试策略 | `retry.py`（统一重试壳） + `openai_provider.py` / `anthropic_provider.py`（协议特异处理） |

## CONVENTIONS

- 模型名格式：`provider/model`（如 `anthropic/claude-sonnet-4-20250514`），前缀自动剥离
- Provider 名可自定义（如 `my-proxy/claude-sonnet-4-6`）
- 所有 Provider 支持第三方代理，SDK 兼容性自动处理
- `reasoning_effort` 处理约定：`off` 时显式关闭推理扩展（Anthropic/Gemini 不发送 thinking，OpenAI/Codex 统一映射为官方 `none`）；`low/medium/high` 时，Anthropic 映射为 `budget_tokens=2048/4096/8192` 且默认使用 `thinking.type="adaptive"`（未显式设置时，支持 thinking 的模型默认 `adaptive + 1024`），Gemini 映射为 `thinking_budget=1024/2048/4096`，OpenAI/Codex 透传 effort
- `service_tier` 处理约定：OpenAI-family provider 只做标准化与单路径透传，不在 provider 层私自发明“fastmode”别名；桌面/主代理/子代理/utility/startup/heartbeat 都复用同一个上游配置值
- `openai_codex` 仅支持显式前缀路由（`openai-codex/*` 或 `openai_codex/*`），不应依赖模型名包含 `codex` 的模糊匹配
- Responses 工具调用约定：`call_id` 归一化、internal `tool_call_id` 构造、以及 SSE tool-call 聚合统一放在 `responses_compat.py`；provider 不应各自复制或改写这套规则
- OpenAI 风格 assistant `tool_calls` 消息统一经 `ToolCallRequest.to_openai_tool_call()` 产出，避免 loop/subagent/provider 各自复制序列化逻辑；仅在 `argument_parse_error` 仍存在时保留原始 `raw_arguments` 回写，修复成功后的参数一律回写规范化 JSON
- Provider/tool 契约必须说真话：参数成功解析时 `arguments` 是规范化对象；参数失败时同时携带 `raw_arguments` 与 `argument_parse_error`，下游据此显式失败，不能再把“调用方没传参数”和“provider 解析坏了”混成一类
- 截图 `_image` 字段处理约定：消息中的 `_image` 字段（base64 JPEG）由 `context.add_tool_result` 注入；各 Provider 在消息转换时检测并转为原生格式 — Anthropic 在 tool_result content 内嵌 image block（无需 flush），OpenAI/Gemini/Responses API 采用延迟批量 flush 模式（收集 pending images → 在下一个非 tool 消息前或消息列表末尾插入单条 user message）；`_image` 在 `provider.chat()` 返回后由调用方 `pop` 清除
- 流式中断约定：Provider 必须透传 `ProgressCallbackError` 子类；当收到 `StreamInterruptedError` 时返回 `LLMResponse(finish_reason="interrupted", content=content or None)`，不得吞掉 `asyncio.CancelledError`；retry 分支中的中断路径语义需与主路径一致

## ANTI-PATTERNS

- 不要同步 import Provider SDK → 延迟加载是核心设计
- 不要硬编码模型名 → 走配置
