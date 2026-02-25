<div align="center">

<br>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/hero.svg" />
  <source media="(prefers-color-scheme: light)" srcset="assets/hero.svg" />
  <img alt="bao" src="assets/hero.svg" width="800" />
</picture>

<br>

**~7,000 行核心代码** · 记忆永不消失 · 经验持续积累 · 智能不断进化

[🇨🇳 中文](#为什么选-bao) · [🇺🇸 English](#-english)

</div>

<br>

## 为什么选 bao？

大多数 AI 助手都有失忆症。每次对话从零开始，反复犯同样的错，记不住你的偏好，永远学不会。

bao 不一样。它**记得住**、**学得会**、**能进化**。

<p align="center"><img src="assets/features.svg" width="800" alt="核心特性"></p>

### 记忆不会消失

基于 **LanceDB** 的持久化记忆 — 向量搜索 + 关键词降级，双检索架构。有没有 Embedding 模型都能用。

你的偏好、你的项目、你的习惯，bao 全部记住。旧上下文自动整合，重要信息跨会话、跨重启永久留存，过时内容主动清理。

### 经验持续积累

内置**闭环经验引擎**：

- 每次任务完成 → 自动提取教训、策略和失败模式
- 遇到类似问题 → 检索相关经验，注入到提示词中
- **置信度校准** — Laplace 平滑追踪成功率，避免冷启动偏差，动态调整质量分
- **冲突检测** — 发现矛盾的教训时自动标记
- **负面学习** — 过去的失败变成未来的警告
- **主动遗忘** — 按质量分级衰减（高质量保留更久），高价值经验免疫清理

别的 Agent 重复犯错。**bao 从错误中进化。**

### 思考更有深度

- **Thinking Protocol** — 深度推理协议内置于系统提示词。零额外 API 调用，回答质量显著提升
- **Retry with Reflection** — 自动检测工具报错并重试。连续 3 次失败后，升级为完整的策略反思
- **Dynamic Tool Hints** — 根据实际可用性动态启停工具提示。杜绝幻觉工具调用

### 复杂任务不阻塞

把耗时任务丢给子代理，主对话继续聊。不用干等，不用切窗口。

- **后台执行** — 子代理独立运行，主代理随时响应你的新消息
- **进度可查** — 主代理调用 `check_tasks` 即可查看子代理当前阶段、已用工具数、迭代轮次
- **里程碑推送** — 子代理每 5 轮自动汇报一次进展，不刷屏，关键节点不遗漏
- **随时取消** — 任务跑偏了？`cancel_task` 一键终止
- **卡死检测** — 超过 2 分钟无更新自动标记警告，不会悄悄挂住

一个助手，同时处理多件事。**你问进度，它答得上来。**

### ⌨️ 原生 OpenCode + Codex + Claude Code 编程代理

想让 bao 直接帮你写代码、改代码、排错代码？现在开箱即用：

- **`opencode` 工具** — 一句话委托编程，支持会话续接、重试与超时保护，复杂任务也能稳步推进
- **`opencode_details` 工具** — 默认结果简洁省 token；需要排错细节时，按 `request_id` 一键拉取完整 stdout/stderr
- **`opencode` skill** — 内置可复用编程流程（需求澄清 → 实现 → 验证），上手更快、成功率更高
- **`codex` 工具** — 非交互执行编程任务，支持会话续接与输出预算控制，适合连续迭代开发
- **`codex_details` 工具** — 默认回复保持精简，需要深度排错时按 `request_id` 拉取完整详情
- **`codex` skill** — 标准化 Codex 编程工作流（执行 → 续写 → 详情回查），降低误操作并提升交付稳定性
- **`claudecode` 工具** — 基于 `claude -p` 非交互执行编程任务，按官方 JSON `session_id` 稳定续接（`session_id` / `resume`）并返回结构化输出
- **`claudecode_details` 工具** — 默认输出精简，按 `request_id` 或 `session_id` 拉取原始 JSON stdout + stderr 详情

### 极致轻量

**~7,000 行核心代码。** 运行 `bash core_agent_lines.sh` 自行验证。

启动快、占资源少、源码可读。一个完整的 AI 助手框架，体积只有同类项目的 1%。
### 上下文不会爆炸
内置分层上下文管理，长任务不再耗尽 context window：
- **Layer 1**：tool 输出超过阈值自动外置到本地文件，messages 中只保留预览+指针
- **Layer 2**：context 过大时自动压实，保留最近 N 对 assistant/tool 消息，严格维护成对完整性
配置 `contextManagement: "auto"` 即可启用，默认 `observe` 模式零额外开销。
### 长任务越跑越稳

别的 Agent 跑长任务时越跑越迷。bao 越跑越清醒。

- **轨迹压缩** — 每 5 步自动压实执行状态，保留结论、证据和未探索分支。不会因为步骤多而迷失方向
- **自我纠错** — 连续失败 2 次后，压缩时自动注入审计指令：哪里错了、怎么纠正。零额外 LLM 调用，不加延迟不加开销
- **充分性检查** — 自动判断已有信息是否足够回答。够了就停，不多走一步废路

同样的任务，别人的 Agent 在第 10 步开始兆圈。**bao 在第 10 步压缩状态、纠正方向、继续前进。**

## 横向对比

| | OpenClaw | **bao** |
|---|---|---|
| 语言 | TypeScript | **Python** |
| 核心代码 | 430,000+ 行 | **~7,000 行** |
| 记忆 | 仅会话内 | **LanceDB（向量 + 关键词）** |
| 经验学习 | — | **ExperienceLoop** |
| 自我反思 | — | **Thinking Protocol + Retry** |
| 开放问题 | 8,400+ | **稳定且专注** |
| 后台任务 | — | **子代理 + 进度追踪 + 里程碑推送** |
| 长任务引擎 | — | **轨迹压缩 + 自我纠错 + 充分性检查** |
| 上手时间 | 复杂引导 | **2 分钟** |

<p align="center"><img src="assets/architecture.svg" width="800" alt="架构"></p>

## 🚀 快速开始

```bash
pip install bao-ai
bao
```

首次运行自动生成配置文件。在 `~/.bao/config.jsonc` 中设置你的 API Key：

```json
{
  "providers": {
    "openaiCompatible": {
      "apiKey": "sk-or-v1-xxx"
    }
  }
}
```

再次运行：

```bash
bao
```

**就这样。2 分钟，一个完整的 AI 助手。**


可选：配置一个**效用模型**用于后台任务（经验提取、记忆整合、会话标题生成），节省开销：

```json
{
  "agents": {
    "defaults": {
      "model": "anthropic/claude-sonnet-4-20250514",
      "utilityModel": "openrouter/google/gemini-flash-1.5"
    }
  }
}
```

## 💬 9 大聊天平台

一份配置，一条命令：`bao`

| 平台 | 配置方式 |
|------|---------|
| **Telegram** | @BotFather 获取 Token |
| **Discord** | Bot Token + Message Content Intent |
| **WhatsApp** | 扫码连接 |
| **飞书** | App ID + App Secret |
| **Slack** | Bot Token + App-Level Token |
| **Email** | IMAP/SMTP 凭据 |
| **QQ** | App ID + App Secret |
| **钉钉** | App Key + App Secret |
| **iMessage** | 仅 macOS，零配置 |

每个平台渲染能力不同，bao 心里有数。Telegram 和 Discord 收到格式丰富的 Markdown；Slack 和飞书走各自的标记子集；iMessage、QQ、Email 则是干净的纯文本 — 没有满屏的 `**` 和 `###`。**同一个 AI，9 种最佳阅读体验。**

## 🤖 LLM Provider

极简 3 类覆盖 99% 需求。

| 类型 | 支持的模型 | 示例 |
|------|-----------|------|
| **OpenAI 兼容** | OpenAI、OpenRouter、DeepSeek、Groq、SiliconFlow、火山引擎、DashScope、Moonshot、智谱、Ollama、LM Studio、vLLM 等 | `openai/gpt-4o`、`deepseek/deepseek-chat` |
| **Anthropic** | Claude 全系列 | `anthropic/claude-sonnet-4-20250514` |
| **Gemini** | Gemini 全系列 | `gemini/gemini-2.0-flash-exp` |

Provider 名称可自定义（如 `my-proxy/claude-sonnet-4-6`），前缀自动剥离。所有 Provider 类型均支持第三方代理，SDK 兼容性自动处理。OpenAI 兼容端点额外支持 API 模式自动探测（Responses / Chat Completions）。

## 🔌 MCP 支持

Model Context Protocol — 接入任何工具生态。配置兼容 **Claude Desktop 和 Cursor**：

```json
{
  "tools": {
    "mcpMaxTools": 50,
    "mcpSlimSchema": true,
    "mcpServers": {
      "filesystem": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path"]
      }
    }
  }
}
```

`mcpMaxTools` 用于限制 MCP 工具总注册数（`0` 表示不限制）；`mcpSlimSchema` 用于精简 MCP schema 的冗余元数据，减少 token 占用。

## 🐳 Docker

```bash
vim ~/.bao/config.jsonc
docker compose up -d bao-gateway
```

## 💬 聊天命令

全平台通用：

| 命令 | 说明 |
|------|------|
| `/new` | 新建对话（旧对话自动保留） |
| `/session` | 列出所有对话，按编号选择（含自动标题） |
| `/delete` | 删除当前对话 |
| `/model` | 切换模型 |
| `/help` | 显示可用命令 |

首轮对话后，bao 自动生成简短的会话标题，跟随用户语言。

## 🖥️ CLI

| 命令 | 说明 |
|------|------|
| `bao` | 启动所有平台通道（首次运行自动初始化） |

## 🖥️ Desktop App (实验性)

基于 PySide6 + QML 的桌面客户端，`bao` CLI 的纯 UI 壳子。核心逻辑（AgentLoop、Channels、Cron、Heartbeat）全部复用 `bao/` core，不重复实现。

```bash
uv sync --extra desktop
uv run python app/main.py
```

首次启动自动创建 `~/.bao/config.jsonc` 与 workspace；未配置 Provider/Model 时自动跳转 Settings。详见 [`app/README.md`](app/README.md)。打包说明见 [`docs/desktop-packaging.md`](docs/desktop-packaging.md)。
## 📁 项目结构

```
bao/
├── agent/          # 核心 Agent 逻辑
│   ├── loop.py     # Agent 循环（思考 + 重试 + 经验）
│   ├── context.py  # 提示词组装 + 经验注入
│   ├── memory.py   # LanceDB 持久记忆
│   ├── subagent.py # 后台任务执行
│   └── tools/      # 内置工具（Shell、文件、Web、OpenCode、Codex、Claude Code、MCP）
├── skills/         # 可扩展技能系统
├── channels/       # 9 大平台集成
├── providers/      # 3 种 LLM Provider
├── session/        # 多会话管理（LanceDB 持久化）
├── bus/            # 异步消息路由
├── cron/           # 定时任务
└── cli/            # 命令行界面
```

<br>

<details>
<summary><h2>🇺🇸 English</h2></summary>

<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/hero-en.svg" />
  <source media="(prefers-color-scheme: light)" srcset="assets/hero-en.svg" />
  <img alt="bao" src="assets/hero-en.svg" width="800" />
</picture>

<br>

**~7,000 lines of core code** · Memory that persists · Experience that compounds · Intelligence that evolves

</div>

<br>

### Why bao?

Most AI assistants have amnesia. Every conversation starts from zero. They repeat the same mistakes, forget your preferences, and never improve.

bao is different. It **remembers**, **reflects**, and **evolves**.

<p align="center"><img src="assets/features-en.svg" width="800" alt="Core Features"></p>

#### Memory That Stays

Persistent memory powered by **LanceDB** — vector search with keyword fallback. Dual retrieval that works with or without an embedding model.

Your preferences, your projects, your patterns — bao remembers all of it. Old context consolidates automatically. Important details survive across sessions, across restarts, indefinitely. Stale content is actively cleaned up.

#### Experience That Compounds

bao ships with a **closed-loop experience engine**:

- After every task → auto-extracts lessons, strategies, and failure patterns
- Before similar tasks → retrieves relevant experience and injects it into the prompt
- **Confidence calibration** — Laplace-smoothed success tracking, no cold-start bias, dynamic quality adjustment
- **Conflict detection** — flags contradictory lessons
- **Negative learning** — past failures become warnings
- **Active forgetting** — quality-based retention decay (high-quality lasts longer), high-value experiences immune from cleanup

Other agents repeat mistakes. **bao learns from them.**

#### Thinking That Goes Deep

- **Thinking Protocol** — deep reasoning baked into the system prompt. Zero extra API calls, measurably better answers
- **Retry with Reflection** — auto-detects tool errors. After 3 consecutive failures, escalates to a full strategy pivot
- **Dynamic Tool Hints** — enables and disables tool suggestions based on actual availability. No hallucinated tool calls

#### Complex Tasks, Zero Blocking
Hand off time-consuming work to a subagent. Keep chatting. No waiting, no window-switching.
- **Background execution** — subagents run independently while the main agent stays responsive to you
- **Progress on demand** — the main agent calls `check_tasks` to see current phase, tool count, and iteration progress
- **Milestone updates** — subagents auto-report every 5 iterations. No spam, no missed beats
- **Cancel anytime** — task going sideways? `cancel_task` kills it instantly
- **Stall detection** — flags a warning if no update in 2+ minutes. Nothing hangs silently
One assistant, multiple jobs in flight. **Ask about progress — it always has an answer.**

#### ⌨️ Built-in OpenCode + Codex + Claude Code Coding Agents

Want bao to actually write, refactor, and debug code for you? It ships ready-to-use:

- **`opencode` tool** — delegate coding in one line, with session continuity, retries, and timeout safety
- **`opencode_details` tool** — keep default replies compact, then pull full stdout/stderr by `request_id` when needed
- **`opencode` skill** — reusable coding playbook (clarify → implement → verify) for faster, safer execution
- **`codex` tool** — non-interactive coding execution with session continuity and output-budget guardrails
- **`codex_details` tool** — keep default replies concise, then fetch full details by `request_id` when needed
- **`codex` skill** — Codex-first workflow (execute → continue → inspect details) for reliable iterative coding
- **`claudecode` tool** — non-interactive coding execution via `claude -p`, resuming with canonical `session_id` from official JSON output (`session_id` / resume)
- **`claudecode_details` tool** — keep default replies concise, then fetch raw JSON stdout + stderr details by `request_id` or `session_id`

#### Ultra Lightweight

**~7,000 lines of core code.** Run `bash core_agent_lines.sh` to verify.

Fast startup. Low resource use. Readable source. A complete AI assistant framework at 1% the size of comparable projects.
### Context That Doesn't Explode
Built-in layered context management keeps long tasks from exhausting the context window:
- **Layer 1**: Large tool outputs are offloaded to local files; messages retain only a preview + pointer
- **Layer 2**: When context grows too large, older assistant/tool pairs are archived, preserving strict pairing integrity
Set `contextManagement: "auto"` to enable. Default `observe` mode has zero overhead.
### Long Tasks That Stay on Track
Other agents lose the plot on long tasks. bao gets sharper with every step.
- **Trajectory compression** — Every 5 steps, execution state is auto-compressed into conclusions, evidence, and unexplored branches. No drifting, no forgetting
- **Self-correction** — After 2+ consecutive failures, the compression pass injects an audit: what went wrong and how to fix it. Zero extra LLM calls, zero added latency
- **Sufficiency check** — Automatically detects when enough information has been gathered. Stops when done, never wastes steps on dead ends
Same task, other agents start going in circles at step 10. **bao compresses state, corrects course, and keeps moving.**

### How It Compares

| | OpenClaw | **bao** |
|---|---|---|
| Language | TypeScript | **Python** |
| Core code | 430,000+ lines | **~7,000 lines** |
| Memory | Session-only | **LanceDB (vector + keyword)** |
| Experience learning | — | **ExperienceLoop** |
| Self-reflection | — | **Thinking Protocol + Retry** |
| Open issues | 8,400+ | **Stable & focused** |
| Background tasks | — | **Subagent + progress tracking + milestone push** |
| Long-task engine | — | **Trajectory compression + self-correction + sufficiency check** |
| Setup time | Complex wizard | **2 minutes** |

<p align="center"><img src="assets/architecture-en.svg" width="800" alt="Architecture"></p>

### 🚀 Quick Start

```bash
pip install bao-ai
bao
```

First run auto-generates a config file. Set your API key in `~/.bao/config.jsonc`:

```json
{
  "providers": {
    "openaiCompatible": {
      "apiKey": "sk-or-v1-xxx"
    }
  }
}
```

Run again:

```bash
bao
```

**That's it. 2 minutes to a working AI assistant.**


Optional: configure a **Utility Model** for background tasks (experience extraction, memory consolidation, session title generation) to save costs:

```json
{
  "agents": {
    "defaults": {
      "model": "anthropic/claude-sonnet-4-20250514",
      "utilityModel": "openrouter/google/gemini-flash-1.5"
    }
  }
}
```

### 💬 9 Chat Platforms

One config, one command: `bao`

| Platform | Setup |
|----------|-------|
| **Telegram** | Token from @BotFather |
| **Discord** | Bot Token + Message Content Intent |
| **WhatsApp** | Scan QR code |
| **Feishu** | App ID + App Secret |
| **Slack** | Bot Token + App-Level Token |
| **Email** | IMAP/SMTP credentials |
| **QQ** | App ID + App Secret |
| **DingTalk** | App Key + App Secret |
| **iMessage** | macOS only, zero config |
Every platform renders differently — bao knows that. Telegram and Discord get rich Markdown. Slack and Feishu get their native markup. iMessage, QQ, and Email get clean plain text — no raw `**` or `###` cluttering the screen. **One AI, nine tailored reading experiences.**

### 🤖 Easy LLM Providers config

Covers 99% of what's out there.

| Type | Supported Models | Example |
|------|------------------|---------|
| **OpenAI Compatible** | OpenAI, OpenRouter, DeepSeek, Groq, SiliconFlow, Volcengine, DashScope, Moonshot, Zhipu, Ollama, LM Studio, vLLM, and more | `openai/gpt-4o`, `deepseek/deepseek-chat` |
| **Anthropic** | Full Claude lineup | `anthropic/claude-sonnet-4-20250514` |
| **Gemini** | Full Gemini lineup | `gemini/gemini-2.0-flash-exp` |
Provider names are customizable — model prefixes are auto-stripped. All provider types support third-party proxies with automatic SDK compatibility. OpenAI-compatible endpoints also support API mode auto-detection (Responses / Chat Completions).

### 🔌 MCP Support

Model Context Protocol — plug into any tool ecosystem. Config format is **compatible with Claude Desktop and Cursor**:

```json
{
  "tools": {
    "mcpMaxTools": 50,
    "mcpSlimSchema": true,
    "mcpServers": {
      "filesystem": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path"]
      }
    }
  }

`mcpMaxTools` caps the total number of MCP tools registered (`0` = unlimited). `mcpSlimSchema` strips redundant schema metadata to reduce token usage.
}
```

### 🐳 Docker

```bash
vim ~/.bao/config.jsonc
docker compose up -d bao-gateway
```

### 💬 Chat Commands

Available across all platforms:

| Command | What it does |
|---------|-------------|
| `/new` | Start a new conversation (old one is preserved) |
| `/session` | List all conversations with auto-generated titles, pick by number |
| `/delete` | Delete current conversation |
| `/model` | Switch model |
| `/help` | Show available commands |

After the first exchange, bao auto-generates a short session title using a lightweight model, matching the user's language.

### 🖥️ CLI

| Command | What it does |
|---------|-------------|
| `bao` | Start all platform channels (auto-initializes on first run) |

### 🖥️ Desktop App (experimental)
PySide6 + QML desktop client — a pure UI shell for `bao`. All core logic (AgentLoop, Channels, Cron, Heartbeat) reuses `bao/` core, no duplication.
```bash
uv sync --extra desktop
uv run python app/main.py
```
First launch auto-creates `~/.bao/config.jsonc` and workspace; redirects to Settings if Provider/Model is not configured. See [`app/README.md`](app/README.md). Packaging guide: [`docs/desktop-packaging.md`](docs/desktop-packaging.md).
### 📁 Project Structure

```
bao/
├── agent/          # Core agent logic
│   ├── loop.py     # Agent loop (thinking + retry + experience)
│   ├── context.py  # Prompt assembly + experience injection
│   ├── memory.py   # LanceDB persistent memory
│   ├── subagent.py # Background task execution
│   └── tools/      # Built-in tools (shell, files, web, OpenCode, Codex, Claude Code, MCP)
├── skills/         # Extensible skill system
├── channels/       # 9 platform integrations
├── providers/      # 3 LLM provider types
├── session/        # Multi-session management (LanceDB persistence)
├── bus/            # Async message routing
├── cron/           # Scheduled tasks
└── cli/            # Command line interface
```

</details>

<br>

<div align="center">

<sub>bao — 记得住的 AI 助手。</sub>

</div>
