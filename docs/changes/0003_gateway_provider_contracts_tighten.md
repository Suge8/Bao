# 当前进度

- gateway frame 已收紧：按 type 绑定具体 payload schema（hello/welcome/event/replay_request/error）。
- provider JSON-RPC 契约补齐：delta/cancel/methods 索引 schemas 已落盘。

# 改动记录（最近）

- [FEAT] 2026-02-05 收紧 gateway frame schema（payload 与 type 绑定）
- [FEAT] 2026-02-05 增加 provider JSON-RPC 契约 schemas（delta/cancel/methods）

# 未来发展（优先级）

P0

- 为 gateway 加入 pairing/鉴权的最小 schema（token 生成/撤销）并写入 audit_events。
- provider JSON-RPC：明确 method 命名空间与通知（notification）规则（例如 provider.delta 仅通知、无 id）。

P1

- 将 schema-tests 扩展为：校验 dimsums/*/manifest.json 也必须符合 dimsum manifest schema。
