# Bao

Bao 是一个本地优先（desktop-first）的 Agent 框架与应用：

- 桌面端（Tauri）是唯一主入口：对话、任务、点心、记忆、设置、日志。
- 桌面运行即 Gateway：移动端通过局域网或远程隧道连接。
- 点心（Dimsum）支持 `wasm` / `process` 两类运行时，核心保持 thin-waist。
- 记忆系统采用 native 路线（SQLite + Blob），支持演化与可回滚。

## 当前阶段

- 当前为 **Stage 2 可用基线**：核心闭环 + 发布门禁 + 关键可观测能力已打通（Chat/Tasks/Memory/Dimsums/Gateway/Scheduler）。
- provider 路径已支持中途工具调用（单工具与并发批量），process runner 已补齐进程树采样，memory.extract 已加入语义冲突去漂移策略。

详见：

- `docs/PRD.md`
- `docs/changes/0003_gateway_provider_contracts_tighten.md`

## 常用命令

- `pnpm lint`
- `pnpm build`
- `pnpm test`
- `pnpm test:e2e`
- `cargo test --workspace`

## 开发环境补充

- 首次运行 e2e 前安装浏览器：`pnpm -C apps/desktop exec playwright install`
- CI/新环境如遇 pnpm build scripts 被跳过，请确认根目录 `package.json` 的 `onlyBuiltDependencies` 未被覆盖（当前允许 `esbuild`、`unrs-resolver`）
