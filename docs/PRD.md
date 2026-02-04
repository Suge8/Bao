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
