# Bao — Stage 1（集成可运行）

本文件定义 **Bao 阶段1** 的工程契约：在保留 Stage0 目录与协议稳定性的前提下，把桌面端核心链路（对话/任务/记忆/点心/网关）接线为可运行实现，并保持可审计、可回放、可回归。

## 1. 仓库形态（不可变）

- Monorepo：pnpm + turborepo。
- 桌面端：Tauri + React + Vite + shadcn/ui + framer-motion。
- 移动端：apps/mobile（Expo）保留。
- Rust：Core/网关/存储/插件系统主语言。
- 禁止：任何 admin-web / 浏览器面板；桌面端 IPC 禁止 HTTP/SSE。

## 2. 通信与事件（确定性）

- Desktop 内部：仅 Tauri invoke（请求-响应）与 Tauri event（发布-订阅）。
- Mobile：通过 WebSocket Gateway 连接桌面运行的 gateway。
- 事件统一：`BaoEvent (bao.event/v1)`，并写入 `events` 表用于回放。

### 2.1 桌面端命令面（Stage1 实际提供）

- 会话/对话：`sendMessage` / `createSession` / `listSessions` / `runEngineTurn`
- 任务：`listTasks` / `createTask` / `updateTask` / `enableTask` / `disableTask` / `runTaskNow`
- 点心：`listDimsums` / `enableDimsum` / `disableDimsum`
- 记忆：`listMemories` / `searchIndex` / `getItems` / `getTimeline` / `listMemoryVersions` / `applyMutationPlan` / `rollbackVersion`
- 设置：`getSettings` / `updateSettings`
- 网关：`gatewayStart` / `gatewayStop` / `gatewaySetAllowLan` / `generatePairingToken`
- MCP Bridge：`mcpListTools` / `mcpCallTool`
- Skills 资源：`resourceList` / `resourceRead`
- 全局停止：`killSwitchStopAll`

## 3. 点心（Dimsum）

- 运行时仅允许：`wasm` 与 `process`。
- Router / Memory / Corrector / Provider 保持点心化边界。
- Stage1 执行器使用 `ProcessToolRunner`（替代 mock runner），支持超时与 kill group。

## 4. skills 仓库处理（确定性）

- `SKILL.md` 作为 promptpack 入口。
- 其余文件归类为 resourcepack，只读、可检索、不可自动执行。
- 任何执行必须通过显式工具并受权限与审计控制。

## 5. Memory Native（强约束）

- 真相源：SQLite（结构化）+ Blob（大对象）。
- 点心只提交 `MemoryMutationPlan`，由 core/gateway 执行并写 `audit_events`。
- Progressive Disclosure：`searchIndex -> getTimeline -> getItems`。

## 6. Scheduler/Heartbeat（强约束）

- Scheduler 以 tick 扫描到期任务。
- 到期任务仅执行显式 `dimsumId + toolName + args`。
- 所有执行写 `events` 与 `audit_events`，支持 kill switch。

### 6.1 现状（Stage1）

- 桌面端启动 scheduler tick（默认 1s），从 SQLite 拉取 due tasks 并触发 `ProcessToolRunner`。
- Kill Switch 已接入：可终止正在执行任务组并停止 scheduler/gateway。
- 事件流通过 `events` 表回放为 `bao:event`，桌面与移动端可实时收到。
- 任务执行写入 `events` 与 `audit_events`；run-now 可立即触发执行。
- 记忆 mutation/rollback 已落库并写入 `audit_events`，并支持按版本列表选择回滚目标。
- Chat 已接通 `runEngineTurn`：输入会触发默认 Router/Memory/Corrector/Provider 流程并回写事件。
- `runEngineTurn` 在非 must-trigger 场景会按 settings 调用 provider dimsum process(JSON-RPC)（OpenAI/Anthropic/Gemini/xAI）。
- Settings 可直接维护 `provider.active/model/baseUrl/apiKey`，与运行时调用一致。
- 新增 `bao-dimsum-process`：bundled provider/skills-adapter/mcp-bridge 具备可执行 JSON-RPC 进程实现。
- `runEngineTurn` 非工具分支优先走 provider dimsum process(JSON-RPC)执行，保持点心边界一致。
- `runEngineTurn` 在 `needsMemory=true` 时会真实调用 `searchIndex/getItems` 组装记忆上下文，不再使用本地占位注入。
- `bao.bundled.mcp-bridge` 已提供 `bridge.list_tools/bridge.call_tool`，支持 stdio/http MCP server 桥接。
- 新增 `resourceList/resourceRead` 桌面命令，已接通 `bao.bundled.skills-adapter` process JSON-RPC。
