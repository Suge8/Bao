# Bao

Bao 是一个本地优先（desktop-first）的 Agent 框架与应用：

- 桌面端（Tauri）是唯一主入口：对话、任务、点心、记忆、设置、日志。
- 桌面运行即 Gateway：移动端通过局域网或远程隧道连接。
- 点心（Dimsum）支持 `wasm` / `process` 两类运行时，核心保持 thin-waist。
- 记忆系统采用 native 路线（SQLite + Blob），支持演化与可回滚。

## 当前阶段

- 当前为 **Stage 1 集成可运行**：核心闭环可用（Chat/Tasks/Memory/Dimsums/Gateway/Scheduler）。
- 尚未达到“100% 产品级”：仍有 Stage 2 深化项（provider/tool-calling 覆盖、进程观测细化、大规模记忆演化评测、真后端 e2e）。

详见：

- `docs/PRD.md`
- `docs/changes/0003_gateway_provider_contracts_tighten.md`

## 常用命令

- `pnpm lint`
- `pnpm build`
- `pnpm test`
- `pnpm test:e2e`
- `cargo test --workspace`
