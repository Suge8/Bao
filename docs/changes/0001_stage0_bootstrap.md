# 当前进度

- 阶段0骨架已完成：monorepo/turbo、Rust workspace stubs、schemas、SQLite migration、desktop UI 壳。
- 阶段1补齐：bundled dimsums 目录契约与 manifest stubs；skills 资源工具 schemas。

# 改动记录（最近）

- [FEAT] 2026-02-05 阶段0骨架：schemas 落盘 + SQLite migration + Rust workspace stubs + 桌面 UI 壳（侧边栏/页面占位）
- [FEAT] 2026-02-05 阶段1（早期）：bundled dimsums 目录与 manifest stubs；新增 resource.list/resource.read schemas

# 未来发展（优先级）

P0

- 定稿 Bao 工具/事件/任务/记忆 schemas 的 $id/$ref 策略（URL vs 非 URL），并统一校验工具链。
- 定义 dimsum 安装/启用/不可卸载（bundled）策略的核心 API（bao-engine + storage）。

P1

- gateway（WebSocket）接口与最小握手协议 schema。
- skills-adapter/mcp-bridge 的最小可运行 process 实现（受权限+审计）。

Done/Archive

- 阶段0：baseline 已提交（见 git history）。
