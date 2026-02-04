# Bao — AGENTS.md

## 使命

Bao 是一个世界级的本地桌面 Agent 框架与应用（目标：世界级开源软件）：

- 只有一个桌面应用（Tauri），提供：对话、任务、点心、记忆、设置、日志
- 桌面应用运行即是 Gateway：移动端在同局域网（或用户配置的远程通道，如 Tailscale / tunnel）可连接桌面，进行对话与管理，并可远程操控电脑完成一切操作（受权限与审计约束）
- 点心（Dimsum）热拔插：社区可独立迭代优化点心；Bao 也可在用户授权下自我优化升级点心（受审计、回归测试、失败回滚约束）
- 核心（core）极小：只保留“薄腰（thin waist）”能力，不把策略写死在 core
- 记忆系统原生（native）：不接入 mem0/claude-mem 产品，但吸收其最强思想（Progressive Disclosure + Memory Evolution Pipeline）

---

## 关键定义（统一术语）

### Dimsum（点心）

点心是 Bao 的插件包（热拔插、可版本化、可审计、可回归测试）。一个点心包可同时提供多种能力类型。

#### 点心能力类型（V1 固定集合）

V1 标准中点心包的 `types` 字段只允许以下值（不可新增、不可自由发挥）：

- `tool`：声明 Tools（JSON Schema），供 LLM 原生 tool calling 或 UI 手动触发
- `pipeline`：声明 pipeline hooks（Router/Memory/Corrector），由 Bao Engine 直接调用，不走 LLM
- `provider`：模型供应商适配器（OpenAI/Anthropic/Gemini/xAI/未来供应商），负责 tool calling 流式解析与回灌
- `promptpack`：提示包（skills/prompts），用于稳定提示注入与风格/规范
- `resourcepack`：资源包（代码/CSV/模板/图片/配置），可被工具读取；绝不自动执行
- `localepack`：语言包（i18n），可被桌面与移动端加载
- `bridge`：桥接包（例如 MCP bridge），将外部协议生态转为 Bao Tools

#### 点心运行时（V1 固定）

- `wasm`：WASI，适合纯逻辑点心（Router/Memory/Corrector、规则/重排等）
- `process`：JSON-RPC over stdio（协议 `bao-jsonrpc/v1`），适合 OS 能力（PTY/外部 CLI/MCP/Playwright）

规则：凡是需要进程/PTY/系统 API 的点心，一律 `process`；凡是纯逻辑/可沙箱的点心，一律 `wasm`。

---

## 系统架构总览

### 桌面端（唯一 UI）

- Tauri（Rust backend）+ React/Vite（UI）
- UI 与内核通信：仅通过 Tauri invoke 与 event（禁止 HTTP/SSE）
- UI 技术栈固定：React + Vite + shadcn/ui + magicui +packages/baseui + framer-motion + i18n

### 内核（Rust Core）

核心只保留薄腰能力：

- Plugin Host（WASM + Process）
- Permissions（能力门禁）
- Audit Log（不可篡改 hash chain）
- Storage（SQLite + Blob Store；Single Source of Truth）
- Event Bus（统一事件流：UI/移动端/回放）
- Scheduler（任务调度 + 心跳 tick；周期任务/自进化/持续开发）
- Engine Skeleton（固定流程骨架，策略由点心决定）
- Memory Native（原生记忆系统：Progressive Disclosure + Evolution Pipeline；点心只能提交变更计划）

---

## Engine（Agent Pipeline）

### 固定流程（不可改）

1) `router.route`（pipeline hook）→ 决定是否必须触发工具（must-trigger）与是否需要检索记忆（needsMemory）  
2) `memory.inject`（pipeline hook）→ 只在需要时注入记忆（最近5轮+摘要+检索记忆；默认 progressive disclosure）  
3) Provider 执行（provider dimsum）→ LLM 对话或 tool calling  
4) Tool 执行（tool dimsums via plugin-host；也包含 UI/任务显式触发的工具执行）  
5) Corrector（pipeline hooks）→ schema/逻辑校验 + 重试（最多一次）  
6) `memory.extract`（pipeline hook）→ 从本轮输入+工具结果抽取结构化记忆，输出变更计划（MemoryMutationPlan）并由 core 执行版本化写入  
7) 事件写入与 UI/移动端实时推送

---

## “世界级”的硬约束

### 1) 必触发（Must-trigger）确定性

当且仅当满足以下条件时，必须执行工具：

- Router 输出 `matched=true`
- Router 输出 `quote` 能在当前 user message 原文中精确 contains 命中
- `policy.mustTrigger=true`
- 点心开关 ON + 权限允许 + provider 支持 tool calling + 工具存在

否则：一律不得执行工具，并返回可观测错误事件（写入 audit）。

### 2) 绝不靠“自然话+JSON”

工具调用必须走 provider 原生 tool calling（OpenAI/Anthropic/Gemini/xAI 等）。  
旧式文本 JSON 只允许作为资源内容展示，不允许作为主链路执行。

### 3) 资源与代码绝不自动执行

任何 resourcepack 或 skills 仓库中包含的 `.py/.js/.csv/...` 都只作为资源存储与检索：

- 默认只读
- 任何执行必须通过显式工具（PTY/CLI/脚本执行点心），并受权限与审计门禁

### 4) 插件性能与隔离（WASM 硬限制）

- 模块缓存：compiled module 按 sha256 复用
- 实例池：`performanceTier=highFrequency` 固定 warm=2
- 按需启动：`performanceTier=lowFrequency` 单次创建、用完销毁
- 资源限制：`maxLinearMemoryBytes` + `fuelPerCall` + `timeoutMs` 必须生效，越界即中止

---

## Memory Native（原生记忆系统：确定性 + 可解释 + 可回滚）

### 核心原则（硬约束）

- Single Source of Truth：所有“事实状态”只在 SQLite（+ Blob）里
- Progressive Disclosure：检索先返回“索引/摘要（MemoryHit）”，需要时再取全文/证据链，省 token、少污染上下文
- Memory Evolution Pipeline：长期记忆写入不是 append，而是“抽取→去重→冲突→合并→版本化（mutations + versions）”

### 模块分层（native + 点心扩展边界）

#### A. Store（存储层，native）

- SQLite：结构化数据、索引元数据、关系
- Blob store：截图/附件/大文本快照/patch 等大对象（artifacts）

#### B. Index（索引层，native）

- FTS5：关键词/短语/过滤（解释性强，速度快）
- Vector：语义召回（可插拔实现；先做 HNSW 本地索引文件）
- Hybrid rank：FTS + vector + recency + importance(score)

#### C. Engine（演化引擎，native）

- Extract：从 messages + observations 抽取候选记忆
- Normalize：归一化（同义、单位、时间表达、命名规范）
- Dedup：近重复检测（embedding + 字符相似 + key match）
- Conflict/Merge：矛盾/更新/过期处理（upsert / supersede / delete）
- Emit Mutations：输出可审计的“变更计划（MemoryMutationPlan）”

#### D. Orchestrator（编排注入，native）

- 默认注入：最近 N 轮 + session summary
- 仅当 Router 判定 `needsMemory=true` 才触发检索
- 注入采用 progressive disclosure（三段式：hits→timeline→items）

#### E. Policy（策略/开关，点心可扩展但不影响真相）

- 什么算“应该记住”
- 哪些字段需要用户确认
- 每个点心能写哪些 namespace 的记忆（隔离边界）
- 点心只能提交 MemoryMutationPlan；core 决定执行与否（权限/审计/危险项确认/回归）

#### F. QA/Regression（回归评测，native）

- golden prompts：must-remember / must-not-remember / conflict cases
- 指标化：precision/recall、重复率、冲突处理正确率、注入命中率、延迟

---

## 数据模型（SQLite 单一真相，V1 必须）

- `messages(id, session_id, role, content, created_at, …)`
- `events(id, session_id, type, payload_json, created_at, …)`
- `artifacts(id, sha256, mime, size, blob_path, created_at, …)`
- `memory_items(id, namespace, kind, title, content, json, score, status, created_at, updated_at, last_injected_at, inject_count, source_hash, …)`
- `memory_versions(id, memory_id, prev_version_id, op, diff_json, created_at, actor)`
- `memory_links(id, memory_id, message_id, event_id, weight, created_at)`
- `vector_meta(memory_id, embedding_model, dim, vec_id, updated_at)`
- `audit_log(id, prev_hash, hash, action, subject_type, subject_id, payload_json, created_at)`

### FTS（V1 必须）

- `messages_fts`
- `memory_fts`
- `resources_fts`

---

## 三段式检索接口（Progressive Disclosure）

- `search_index(query)` → 返回少量 MemoryHit（id + title + snippet + score + tags）
- `get_timeline(filter)` → 返回按时间/来源聚合的线索（解释性强）
- `get_items(ids)` → 返回全文 content/json/关联证据链/版本信息

---

## 变更计划（Evolution Pipeline 的统一 IR）

- `UPSERT(memory_item)`
- `SUPERSEDE(old_id -> new_id, reason)`
- `DELETE(memory_id, reason)`
- `LINK(memory_id <-> evidence message/event/artifact)`

每条 mutation 必须带 `idempotency_key`（防重）。

执行 mutations 必须：

- 写 `memory_versions`
- 写 `audit_log`（hash chain）
- 更新 FTS + vector_meta（向量本体文件可延后实现，但接口必须定）

---

## Scheduler（定时任务/心跳：持续开发与自我进化的基础设施）

### 原则（硬约束）

- Scheduler 由 core 提供，以心跳 tick 驱动（桌面运行时启动）
- Task 执行必须显式：到期任务只做“指定 dimsum tool 的执行”，不得隐式推断
- 所有任务执行都要权限门禁与审计 hash chain
- 自我进化必须“可回归、可回滚、可观察”：失败回滚并写 audit，成功也写 audit

### 任务能力（V1 必须）

- once / interval / cron（cron 可先最小实现，但协议与存储字段必须稳定）
- run-now（手动立即执行）
- enable/disable
- 最近执行记录可从 events/tool_calls/audit 还原

Kill Switch：顶栏可达，能终止正在运行的工具/点心调用与任务执行。

---

## 自我进化（Autonomous Evolution）边界

由内置点心 `bao.bundled.autoevolve` 提供“更新计划生成/回归执行/切换版本/回滚”工具。

- core 不允许点心绕过回归直接更新其他点心
- 回归失败必须回滚到上一个可用版本，并记录原因

---

## MCP 与 skills 生态适配（确定性规则）

### MCP（桥接点心）

Bao 不把 MCP 协议写进 core。  
使用内置点心 `bao.bundled.mcp-bridge`（types 必含 tool + bridge，runtime=process）。

mcp-bridge 负责：

- 连接/启动 MCP server（stdio / http transport）
- 将 MCP tools 映射为 Bao tools：`mcp.<serverId>.<toolName>`
- 执行仍受 Bao 权限门禁（MCP server 声称能做什么不算数，最终以 Bao permissions 为准）

### skills（提示+资源的“技能点心化”）

skills 仓库可能包含非 prompt 文件（py/csv/template/image）。  
Bao 适配规则固定：

- 解析 `SKILL.md`（frontmatter + body）→ 作为 promptpack 元数据与提示片段
- 除 `SKILL.md` 外的所有文件 → 作为 resourcepack 资源
- 资源可被显式工具读取：`resource.list` / `resource.read`（由 skills-adapter 点心提供工具）
- 资源绝不自动执行；执行必须由显式工具触发并受权限控制

---

## 文件与目录约定（Monorepo 固定）

bao/
apps/
desktop/ # Tauri + React UI（唯一桌面 UI）
mobile/ # RN/Expo（移动端）
crates/
bao-api/ # 共享 types & schema helpers
bao-storage/ # SQLite + blob store + migrations
bao-plugin-host/ # WASM/Process runtime host
bao-engine/ # agent pipeline + 内置点心加载 + memory native + scheduler
bao-gateway/ # WebSocket gateway
dimsums/
bundled/ # 内置点心包（随安装分发，不可卸载）
community/ # 示例点心包（可安装）
packages/
baseui/ # UI 组件封装（shadcn/radix 的统一层）
i18n/ # zh/en 内置 + localepack 加载器
schemas/ # JSON Schemas（manifest/router/event/toolcall/permissions/memory/task）
docs/
AGENTS.md
PRD.md
CHANGELOG.md

---

## 存储（SQLite 为单一事实源）

### 必备表（V1）

- sessions
- messages（流式写入，message.done 后定稿）
- tool_calls
- tasks
- memory_items
- memory_versions
- memory_links
- events（eventId 自增，用于回放）
- audit_events（不可篡改 hash chain）
- dimsums（安装/启用/版本/manifest/签名）
- settings
- resources（skills/资源包内容的索引）
- artifacts
- vector_meta

### FTS（V1 必须）

- messages_fts
- memory_fts
- resources_fts

---

## 事件流（BaoEvent）

- 桌面内部：Tauri events（bao:event）
- 移动端：WebSocket 推送同一 BaoEvent JSON
- 断线回放：客户端携带 lastEventId，服务器从 events 表补发

---

## 权限模型（Capabilities）

权限枚举以 `schemas/permissions_v1.json` 为准，任何点心请求权限必须在 manifest 中 `permissionsRequested` 说明原因，UI 必须展示并允许用户开关。

---

## 测试与质量（硬约束）

- 测试优先：新增能力必须有单测或 e2e
- schema 必须校验：manifest/router/toolcall/event/memory/task 全部有校验单测
- 不允许降低校验强度
- 不允许引入 Web 面板
- 桌面 IPC 禁止 HTTP/SSE

---

## 性能指标（V1）

- Router 规则短路 + hook：<= 30ms
- 单工具执行超时：<= 1000ms，最多重试 1 次
- UI 首屏可交互：<= 1000ms（本地冷启动）
- WASM 点心：highFrequency warm=2；lowFrequency 0 warm
- Memory 检索：FTS 命中 <= 30ms；hybrid rank 目标 <= 80ms（可分阶段达成）
- Scheduler tick：默认 1~5s；扫描到期任务 <= 10ms（小规模任务）

---

## 开发规范
- **先读后改**：改动前阅读现有实现，保持结构/命名一致，避免无关重构。
- **不确定先澄清**：需求/边界/验收不清楚必须先问，禁止猜测实现。
- **提交前必做**：任何代码改动必须同步更新 `docs/changes`，必要时更新本文档。
- **记录必填**：每次改动必须更新 `docs/changes` 的「当前进度」「改动记录（最近）」「未来发展（优先级）」（完成项移入 Done/Archive）。
- **格式统一**：`[FEAT|FIX|REFACTOR|DOC] YYYY-MM-DD 事项（PR/issue/commit 链接）`。