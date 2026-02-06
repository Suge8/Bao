# 当前进度

- 阶段0骨架已完成：monorepo/turbo、Rust workspace stubs、schemas、SQLite migration、desktop UI 壳。
- 阶段1补齐：bundled dimsums 已从 manifest stubs 进化为可执行 process；skills 资源工具 schemas 与运行链路已接通。

# 改动记录（最近）

- [FEAT] 2026-02-05 阶段0骨架：schemas 落盘 + SQLite migration + Rust workspace stubs + 桌面 UI 壳（侧边栏/页面占位）
- [FEAT] 2026-02-05 阶段1（早期）：bundled dimsums 目录与 manifest stubs；新增 resource.list/resource.read schemas

# 未来发展（优先级）

P0

- ✅ 已完成（2026-02-06）：Bao 工具/事件/任务/记忆 schemas 的 $id/$ref 策略与统一校验链路已落地。
- ✅ 已完成（2026-02-06）：dimsum 安装/启用/不可卸载（bundled）核心 API 与落库链路已具备。

P1

- ✅ 已完成（2026-02-06）：gateway（WebSocket）接口与最小握手协议 schema 已落地并纳入验证。
- ✅ 已完成（2026-02-06）：skills-adapter/mcp-bridge 最小可运行 process 实现已接通（受权限+审计）。

Done/Archive

- 阶段0：baseline 已提交（见 git history）。
