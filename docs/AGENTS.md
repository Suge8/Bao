# Bao — Stage 0 (骨架)

本文件定义 **Bao 阶段0** 的确定性工程契约。阶段0只做：目录契约、公共 API/traits/stubs、schema 落盘、DB migration 落盘、最小测试框架落地。阶段0不实现完整业务。

## 1. 仓库形态（不可变）

- Monorepo：pnpm + turborepo。
- 桌面端：Tauri + React + Vite + shadcn/ui + framer-motion（依赖已存在）。
- 移动端：apps/mobile（Expo）保留；阶段0仅保持脚手架与目录契约。
- Rust：作为 Core/插件系统核心语言；Rust workspace 可编译。
- 禁止：任何 admin-web / 浏览器面板；桌面端 IPC 禁止 HTTP/SSE。

## 2. 通信与事件（确定性）

- Desktop 内部：只允许 Tauri invoke（请求-响应）与 Tauri event（发布-订阅）。
- Mobile：通过 WebSocket Gateway 连接桌面运行的 gateway；移动端不直接访问桌面 IPC。

事件规范：统一使用 `BaoEvent (bao.event/v1)` schema；桌面 Rust 侧 emit 的 payload 必须可序列化且受权限/审计约束。

### 2.1 桌面端命令面（Tauri commands，目标契约）

桌面端必须提供（命名建议与 UI 对齐，camelCase）：

- `sendMessage(sessionId, text)`
- `listSessions` / `listTasks` / `listDimsums` / `listMemories`
- `getSettings` / `updateSettings`
- gateway: `gatewayStart` / `gatewayStop` / `generatePairingToken`

如 UI 已提供入口，则必须接通：

- tasks: `createTask` / `updateTask` / `enableTask` / `disableTask` / `runTaskNow`
- memory: `searchIndex` / `getItems` / `getTimeline` / `applyMutationPlan` / `rollbackVersion`

## 3. 点心（Dimsum）

- 点心必须热拔插，运行时只允许：`wasm` 与 `process`。
- Router / Memory / Corrector / Provider 全部点心化，并以 **Bundled Dimsums** 随安装分发，语义上不可卸载。

### 3.1 性能与资源限制（WASM，强制）

- 模块缓存：按 wasm bytes 的 sha256 key 复用编译后的 module。
- 实例池：仅 `highFrequency` 点心保留 warm 实例，数量固定 2。
- `lowFrequency`：按需创建实例，用完销毁。
- 限制：`maxLinearMemoryBytes`、`fuelPerCall`、`timeoutMs` 必须生效。

## 4. MCP 接入（确定性）

- MCP 不进入 Core。
- MCP 通过 `mcp-bridge` 点心接入：同一点心包 `types` 同时包含 `tool` 与 `bridge`。
- `mcp-bridge` 必须是 `process` runtime（spawn/连接 MCP transport）。

## 5. skills 仓库处理（确定性）

- `SKILL.md`：唯一作为 promptpack 的入口（metadata + prompt）。
- 其他任意文件（py/ts/js/csv/json/image 等）：一律归类为资源（resourcepack），只允许被显式工具读取；默认只读。
- 任何资源文件的执行必须通过显式 Tool（如 PTY/CLI 或脚本执行点心）并受 permissions + audit 约束；禁止自动执行。

## 6. Memory Native（强约束）

- Single Source of Truth：事实只落 SQLite（结构化）+ Blob（artifacts）。
- 点心不得直接写库：点心只能提交 `MemoryMutationPlan (bao.memory.mutation_plan/v1)`；Core 执行并写审计。
- Progressive Disclosure：检索默认返回 `MemoryHit (bao.memory.hit/v1)`；需要时再拉全文与证据链。
- Evolution Pipeline：Extract→Normalize→Dedup→Conflict/Merge→Versioned Mutations。

## 7. Scheduler/Heartbeat（强约束）

- Scheduler 是一等能力：tick 驱动扫描到期任务。
- 到期任务只执行“显式计划”：指定 `dimsumId + toolName + args`。
- 所有任务执行必须：权限门禁、审计 hash chain、回归（golden prompts/tasks），失败回滚。
- Kill Switch：可终止正在运行的任务/工具。

### 7.1 现状（阶段1落地）

- 桌面端启动 scheduler tick（默认 1s），从 SQLite 拉取 due tasks 并触发 tool 执行（当前 runner 为 mock）。
- Kill Switch 已接入：能终止正在执行的任务组，并停止 scheduler/gateway 任务。
- 事件流通过 `events` 表回放为 `bao:event`，移动端可实时收到。
