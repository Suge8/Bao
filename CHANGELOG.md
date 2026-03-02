# Changelog

All notable changes to Bao are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/), and this project uses [Semantic Versioning](https://semver.org/).

## [0.3.1] - 2026-03-03

### Changed

- **桌面自动化默认启用** — `mss`/`pyautogui`/`pillow-heif` 从可选依赖移入主依赖，`desktop.enabled` 默认 `true`；新用户安装即可用，无需额外步骤
- **配置模板精简** — `toolExposure` 移除 `bundles` 字段（代码默认兜底，不暴露给用户）；桌面自动化注释去掉过时的安装提示

## [0.3.0] - 2026-03-03

### Added

- **计划系统增强** — 计划通知全面本地化，`create_plan` / `update_plan_step` / `clear_plan` 推送按会话语言偏好（中/英）输出；Markdown 渠道发送 Markdown 模板，纯文本渠道自动回退；Slack thread 会话保留线程上下文；渲染安全转义特殊符号
- **流式事件协议** — Agent loop 新增结构化 stream-event 协议，支持外部消费者（UI/自动化）订阅实时进度和工具执行事件
- **工具错误遥测** — 结构化工具错误 telemetry，记录工具选择命中率、参数填充成功率、post-error 调用代理等质量指标
- **一键安装器** — 新增 macOS (`install.sh`) 和 Windows (`install.ps1`) 一键安装脚本，自动检测并补齐 Python/uv 依赖
- **PyPI 发布流程** — 支持 `bao-ai` 包通过 PyPI 分发，`pip install bao-ai` 即可安装

## [0.2.1] - 2026-03-03

### Changed

- **Agent Loop 解耦** — 将 `loop.py` 拆解为多个职责清晰的方法，降低单方法复杂度
- **Subagent Manager 解耦** — 将 `subagent.py` 拆解为聚焦方法，提升可读性和可测试性
- **Coding Agent 解耦** — 将 `coding_agent_base.py` 的 `execute` 方法拆解为多个聚焦方法
- **MCP 连接逻辑提取** — 将 MCP 连接 helper 提取为模块级函数，减少类内耦合
- **启动问候逻辑提取** — 将 `gateway/builder.py` 的启动问候 helper 提取为模块级函数
- **Office 技能共享层** — 提取 `_office_shared` 共享实现，统一 Office validators 的导入契约和 `schemas_dir` 绑定

### Added

- Office validators wrapper 导入契约测试，验证单进程多 skill 连续导入不串线
- Bridge `package-lock.json`，确保 Node 依赖可复现安装

### Docs

- README 补充 planning 工具说明和 office validators 测试用法

## [0.2.0] - 2026-03-03

### Added

- **自动规划系统** — 新增 `create_plan` / `update_plan_step` / `clear_plan` 三个原子工具，AI 遇到多步骤任务自动创建计划并逐步更新
  - Planning 状态模型（`plan.py`）：纯函数式，`Session.metadata` 持久化
  - Agent loop 集成：tool_hints 包含 WHEN/HOW/SKIP 触发策略；活跃计划以 `## Current Plan` 注入上下文，完成后自动归档
  - Context builder 集成：`build_messages()` 接受 `plan_state` 参数，done 时停止注入
  - Planning 测试套件
- **Docker 安全加固** — 非 root 运行、资源限制、health check；新增 WhatsApp bridge 服务（Docker Compose profile）
- **Docker 环境模板** — `.env.docker.example` + `.gitignore` 白名单，Docker 专用配置与本地运行隔离

### Fixed

- CI/CD：修复 macOS runner 配置和 Nuitka 环境变量问题

## [0.1.0] - 2026-03-03

Bao 首个正式版本。

### Core Agent

- **Agent 主循环** — 完整的 agent loop，含 retry with reflection（连续 3 次失败后反思策略）、per-session lock、generation barrier（阻止过期响应发出）
- **协作式软中断** — 同会话新消息通过流式阶段 + 工具启动前 + 工具执行中 + 工具边界四层检查实现软中断；`/stop` 保留为硬中断（natural + active 双 key 取消）
- **长任务引擎** — 轨迹压缩（每 5 步 RE-TRAC 式递归重置）+ T# 编号前缀 + 条件性自审计 + 充分性检查（累计步数 gate，命中后优先禁用 tools 收口）
- **模块提取** — `shared.py`（7 个共享函数）、`commands.py`（/model + /session 命令）、`experience.py`（经验提取逻辑）从 loop.py 独立

### Memory & Experience

- **分类长期记忆** — preference / personal / project / general 四分类独立存储，写入硬帽（`MEMORY_CATEGORY_CAPS`）+ 去重 + 智能截断
- **列式经验引擎** — 闭环学习（Laplace 平滑置信度 + 冲突检测 + 负面学习 + 主动遗忘）、BM25 降级检索、多因子纯 Python rerank、检索命中追踪
- **记忆管理** — `/memory` 交互式斜杠命令（4 状态状态机：list → detail → edit/delete），Gemini embedding 支持
- **条件 LTM 注入** — 按 query 相关性过滤分类，中文 CJK bigram + 混合脚本双提取 tokenizer，记忆/经验预算控制（`MAX_LONG_TERM_MEMORY_CHARS=1500`）

### Context & Prompt

- **分层上下文管理** — Layer 1 大输出外置 + Layer 2 自动压实（保留最近对话轮次 + 最近工具块）
- **用户图片自动压缩** — 大于 1MB 或非原生格式自动 JPEG 压缩（EXIF 修正 + 透明通道合成 + 1568px 长边缩放）
- **渠道格式指引** — 按渠道注入 system prompt，新增渠道需同步添加
- **Runtime Context** — 运行时元数据拼入 system prompt 的 `## Runtime` section
- **Thinking Protocol** — 条件跳过 + channel format hints

### Subagent

- **后台子代理** — 独立运行，主代理随时响应；里程碑推送（每 5 轮自动汇报）
- **进度追踪** — `check_tasks` 双格式输出（brief 单行 + detailed 多行）、`check_tasks_json` 结构化 JSON（schema_version=1）
- **会话续接** — `context_from` 快照前序任务上下文注入新子代理
- **取消 API** — `cancel_task` 请求式取消 + 2 分钟无更新警告标记
- **输出净化** — label/summary/actions 的 `\n`/`\r`/`|` 清洗 + announce 模板含反注入提示
- **编程代理流式进度** — `_read_stream` 增量 UTF-8 解码 → `TaskStatus.recent_actions`

### Tools

- **统一编程代理** — 自动检测 OpenCode/Codex/Claude Code，6 工具合并为 2（`coding_agent` + `coding_agent_details`）；stale session 自动降级；会话缓存 LRU；优雅进程终止（SIGTERM → 2s → SIGKILL）；默认 30 分钟超时
- **消息工具** — ContextVar 注入 + `reply_to` 透传 + 防重发（空内容拦截 + `_sent_in_turn` 标记）+ 默认拒绝向 desktop channel 发送
- **定时任务工具** — ContextVar 注入 + kwargs-based execute + 输入校验
- **MCP 工具桥接** — Schema 精简（`mcpSlimSchema`）+ 工具总量上限（`mcpMaxTools` + per-server `maxTools`）+ 原子注册回滚 + 连接超时
- **桌面自动化** — 7 个原子工具（screenshot/click/type_text/key_press/scroll/drag/get_screen_info），mss + pyautogui 驱动，Retina/HiDPI 自适应
- **AI 图像生成** — Gemini API 文生图 + 多平台发送
- **Web 工具** — 内容过滤 pipeline + Exa 搜索集成
- **工具输出预算** — artifact pipeline + hard clip
- **工具可观测性** — 每轮 schema 体积采样 + 工具质量代理指标（`tool_selection_hit_rate` / `parameter_fill_success_rate`），软中断调用单独计入

### Providers

- **4 类 Provider** — OpenAI 兼容 / Anthropic / Gemini / OpenAI Codex OAuth
- **Gemini 完全重写** — 用户图片支持（`inline_data` Blob）、流式中断
- **Responses API 自动探测** — OpenAI 兼容端点自动切换 Responses / Chat Completions
- **流式进度回调** — 所有 Provider 统一 `on_progress` / `on_tool_hint` 回调
- **Provider 匹配安全** — 前缀命中要求 type 一致；openai 兜底仅在 type 匹配时生效
- **Anthropic data URL 防御** — 畸形 URL 跳过，不发送空 base64

### Channels

- **9 大平台** — Telegram / Discord / WhatsApp / Feishu / Slack / Email / QQ / DingTalk / iMessage
- **Telegram 媒体组聚合** — `media_group_id` 缓冲 0.6s 窗口后合并发送
- **ProgressBuffer** — iMessage / WhatsApp 非流式渠道缓冲 + 去重 + 边界切分
- **Discord** — RESUME 重连 + zombie 连接检测 + typing loop HTTP 失败隔离
- **Feishu** — thread join + `react_emoji` 可配置
- **iMessage 媒体收发** — AppleScript outbound + attachment 表 inbound + 纯媒体消息占位符
- **渠道双语日志** — gateway / cron / heartbeat / artifacts 全面中英双语

### Config

- **SecretStr 凭据保护** — 所有凭据字段统一 `pydantic.SecretStr`，`model_dump()` 输出 `"**********"`
- **JSONC 加载管线** — 5 状态字符级状态机去注释 → 版本化迁移 → env overlay（`BAO_*` 深度合并）→ Pydantic 验证
- **工具暴露控制** — `toolExposure.mode`（off/auto）+ `toolExposure.bundles`（core/web/desktop/code）
- **模板 i18n** — workspace 模板按语言存放 `bao/templates/workspace/{zh,en}/`
- **首次引导** — 双语语言选择 + persona 设置 + workspace 模板写入

### Skills

- **17 个内置技能** — 编程代理、图像生成、PDF、DOCX、XLSX、PPTX、浏览器自动化、天气、定时任务等
- **技能摘要压缩** — 单行格式 + 首句或 60 字符截断 + 换行归一化

### Session

- **原子保存** — 写入 + 校验 + rollback，LanceDB 持久化
- **Active Cache** — 内存字典缓存解决 LanceDB 索引延迟
- **会话标题生成** — 首个/第二个 user turn 后异步生成，问候语过滤 + 中文≤12字/英文≤6词约束
- **用户消息即时持久化** — 双层（run 预存 + _process_message 落库），base64 图片剥离

### Desktop App

- **PySide6 + QML 客户端** — 纯 UI 壳子复用 `bao/` core
- **功能** — 聊天界面、设置页、会话管理、侧边栏、Toast 通知
- **JSONC 写回** — `patch_jsonc()` 新增键插入到 `}` 前，避免注释漂移
- **配置保存稳态** — 异常兜底 + `_valid=True` 同步回写

### CLI

- **ASCII art 面包 banner** — rich 渲染（yellow 面包 + bold cyan 文字）
- **友好日志格式** — 彩色 log format

### Gateway

- **共享构建器** — CLI 和 Desktop 复用 `gateway/builder.py`
- **启动问候** — 每渠道独立 LLM 生成，CJK 本地化时间 + 原生语言 trigger，失败回退 `process_direct(ephemeral=True)`

### Bridge

- **WhatsApp 桥接** — TypeScript/Baileys WebSocket 桥接 + 媒体下载

### Infrastructure

- **CI/CD** — `.github/workflows/desktop-release.yml`（macOS arm64/x86_64 + Windows x64 矩阵构建）
- **Docker** — `docker-compose.yml` + `Dockerfile`（Python + Node 混合构建）
- **测试** — 54 个测试文件，pytest + asyncio_mode=auto

[0.3.0]: https://github.com/Suge8/Bao/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/Suge8/Bao/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/Suge8/Bao/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Suge8/Bao/releases/tag/v0.1.0
