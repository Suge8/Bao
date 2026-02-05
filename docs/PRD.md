# Bao — PRD（Stage 0 骨架）

## 目标

建立世界级项目骨架，使后续 4 个 Agent 可并行开发且互不冲突。阶段0交付物：

- 目录契约与公共 API stubs（Rust crates / packages）。
- 全量 JSON Schema 落盘并可被单测验证。
- SQLite migration `0001_init.sql` 落盘，覆盖：会话/消息/工具调用/任务/事件/审计/点心/设置/资源 + FTS5 + Memory Native 扩展。
- 桌面 UI 空壳可启动（侧边栏 + 页面骨架）。

## 非目标（阶段0禁止）

- 不实现完整业务功能（对话、任务、记忆策略等只做接口/空实现）。
- 不引入 Web 面板或 HTTP/SSE 的桌面端 IPC。

## 关键约束

- Monorepo：pnpm + turborepo。
- 桌面端：Tauri IPC + events。
- 移动端：WebSocket gateway。
- 点心：WASM + Process，两类运行时；Router/Memory/Corrector/Provider 必须点心化且 bundled。
- Memory：native（SQLite+Blob），点心只能提交变更计划。
- Scheduler：tick 驱动，显式计划执行，权限+审计+回归+回滚。

## Stage 0 现状（必须如实）

阶段0的目标是“骨架可编译 + 契约落盘 + 最小测试框架”，因此以下模块在仓库中**可能仍是 stub**：

- `crates/bao-engine`：pipeline hooks / scheduler traits / engine skeleton（已新增最小 scheduler tick + runner 接口）。
- `crates/bao-storage`：Storage 接口已落地最小 SQLite 读取（due tasks + run 记录）。
- `crates/bao-plugin-host`：WASM/Process host 的类型与 trait 占位（已新增 tool runner 接口 + mock runner）。

## Stage 0 桌面端集成要求（后续阶段交付）

桌面端（`apps/desktop/src-tauri`）最终必须把以下能力“接线并跑通”：

- Tauri commands：
  - `sendMessage(sessionId, text)`
  - `listSessions` / `listTasks` / `listDimsums` / `listMemories`
  - `getSettings` / `updateSettings`
  - gateway: `start` / `stop` / `generatePairingToken`
  - tasks: `createTask` / `updateTask` / `enableTask` / `disableTask` / `runTaskNow`
  - memory: `searchIndex` / `getItems` / `getTimeline` / `applyMutationPlan` / `rollbackVersion`
- 桌面 UI 通过 `bao:event` 实时渲染 events。
- Scheduler/心跳：桌面启动时启动 tick；到期任务触发 dimsum tool；写 events/audit；移动端可收到 BaoEvent。
- Kill Switch：可终止正在运行的 tool/task。

## 远程使用最佳实践（强约束）

- 默认仅绑定 `127.0.0.1`。
- 用户显式开启“允许局域网”后才可绑定 `0.0.0.0`。
- 文档与 UI 必须提示：远程请用 Tailscale 或 tunnel；不要裸露公网。

## Stage 1 集成现状（本次补齐）

- desktop-tauri 已接通 tasks/memory 全量 IPC（create/update/enable/disable/runNow + search/getItems/getTimeline/apply/rollback）。
- scheduler tick 已在桌面启动并调用 runner（当前 runner 为 mock）。
- Kill Switch 已接入：停止 scheduler/gateway 并取消正在执行的任务组。
