# 当前进度

- gateway frame 已收紧：按 type 绑定具体 payload schema（hello/welcome/event/replay_request/error）。
- provider JSON-RPC 契约补齐：delta/cancel/methods 索引 schemas 已落盘。
- desktop-tauri：已最小接线 gateway + 事件桥接（bao:event）+ 基础 commands（sendMessage/list*/getSettings/updateSettings）。
- desktop-tauri：新增 tasks/memory IPC（create/enable/disable/runNow + search/getItems/getTimeline/apply/rollback），并补全前端 client 封装与页面联动。
- scheduler：桌面启动 tick 拉取 due tasks 并执行 tool（mock runner），Kill Switch 可终止任务组。
- scheduler：任务执行后更新 next_run_at，once 任务执行后禁用；新增调度时间计算测试。
- desktop-ui：前端 client 不再使用 mock-client，改为仅通过 Tauri IPC 读取 SQLite 数据。

# 改动记录（最近）

- [FEAT] 2026-02-05 收紧 gateway frame schema（payload 与 type 绑定）
- [FEAT] 2026-02-05 增加 provider JSON-RPC 契约 schemas（delta/cancel/methods）
- [FEAT] 2026-02-05 桌面端接线 gateway + bao:event（Tauri commands 最小集）
- [FEAT] 2026-02-05 补齐 tasks/memory IPC + 前端调用链（tauri-client + mock-client + 页面联动）
- [FEAT] 2026-02-05 最小 scheduler tick + kill switch 接通（tool runner mock）
- [FIX] 2026-02-06 任务执行后推进 next_run_at（once 禁用）；补充调度测试
- [FIX] 2026-02-06 前端 client 移除 mock-client，改为纯 Tauri IPC 数据链路

# 未来发展（优先级）

P0

- 为 gateway 加入 pairing/鉴权的最小 schema（token 生成/撤销）并写入 audit_events。
- 补齐 scheduler/task/memory/tool 的真实实现（当前 engine/storage/plugin-host 仍为 stub）。
- 完善 cron/interval 计算与时区覆盖（当前为最小实现）。
- provider JSON-RPC：明确 method 命名空间与通知（notification）规则（例如 provider.delta 仅通知、无 id）。

P1

- 将 schema-tests 扩展为：校验 dimsums/*/manifest.json 也必须符合 dimsum manifest schema。
