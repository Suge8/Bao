# Bao — PRD（Stage 1 集成可运行）

## 目标

在 Stage0 契约稳定的基础上，把桌面端主链路推进到 **可运行、可观测、可回放**：

- 桌面 IPC 命令可真实执行（对话/任务/点心/记忆/设置/网关）。
- Gateway + Scheduler + Storage + Plugin Runner 形成闭环。
- UI 页面从骨架升级为可操作页面（Chat/Tasks/Dimsums/Memory/Settings）。
- 审计链路保持：关键动作写 `events` + `audit_events`。

## 非目标（Stage1 不强制）

- 不要求完成全部产品级体验（如复杂多会话分组、全量 provider 特性、完整可视化日志面板）。
- 不要求实现最终版 Router/Memory/Corrector 点心动态装配（Stage1 允许默认实现）。

## 关键约束

- Monorepo：pnpm + turborepo。
- 桌面端：Tauri invoke + event（禁止 HTTP/SSE IPC）。
- 移动端：WebSocket gateway。
- 点心运行时：WASM + Process。
- Memory：native（SQLite+Blob），变更通过 `MemoryMutationPlan`。
- Scheduler：tick 驱动，执行需审计，可 kill。

## Stage 1 现状（已落地）

- `sendMessage` / `createSession` / `listSessions` 已接通。
- `runEngineTurn` 已接通：
  - 先写入 `message.send` 事件；
  - 调用 engine 默认 turn 流；
  - 命中 must-trigger 时可执行 tool；
  - 写入 `engine.turn` 事件回放。
- tasks 命令链路完整：`list/create/update/enable/disable/runNow`。
- memory 命令链路完整：`searchIndex/getItems/getTimeline/listMemoryVersions/applyMutationPlan/rollbackVersion`。
- dimsum 命令链路完整：`list/enable/disable`。
- gateway 命令链路完整：`gatewayStart/gatewayStop/gatewaySetAllowLan/generatePairingToken`。
- MCP bridge 命令链路已接通：`mcpListTools/mcpCallTool`。
- Skills 资源命令链路已接通：`resourceList/resourceRead`。
- 全局停止：`killSwitchStopAll`。
- Scheduler tick 持续执行 due tasks，写入 events/audit。
- Plugin runner 使用 `ProcessToolRunner`（已替换 mock runner）。
- `runEngineTurn` 非工具路径已接入 provider dimsum process(JSON-RPC)（OpenAI/Anthropic/Gemini/xAI），不再依赖 echo 占位输出。
- Gateway 首启会落 provider/gateway 默认 settings，Settings 页可直接编辑 provider 配置并生效。
- 新增 `bao-dimsum-process`，将 bundled provider/skills-adapter/mcp-bridge 从 manifest-only 推进到可执行 process。
- 对话 provider 路径已改为 process dimsum JSON-RPC 执行，桌面端不直接耦合各 provider HTTP 协议。
- `runEngineTurn` 在 `needsMemory=true` 场景改为真实调用 `searchIndex/getItems` 注入记忆上下文，不再使用字符串占位注入。
- `bao.bundled.mcp-bridge` 已支持 `bridge.list_tools/bridge.call_tool`，可桥接 stdio/http MCP server。
- desktop-tauri 新增真实后端回归测试：`runEngineTurn` 的工具成功链路与 provider 失败链路均在 Rust 侧直接验证 `provider.call.error`/`engine.turn` 可观测性。
- provider 协议覆盖深化：`provider.delta` 方法在 blocking 模式下返回 `done` 终止块；桌面端可解析 `kind=tool_call` 输出并生成可读回显。
- ProcessToolRunner 观测字段增强：输出新增 `pid/startedAtMs/finishedAtMs`，并在 timeout/killed/resource_exceeded 元数据中补充 `pid + startedAtMs + elapsedMs`。
- memory 演化新增大样本压力回归：`crates/bao-gateway/tests/memory_stress_evolution.rs` 覆盖 1200 条 mutation 批量写入、检索、SUPERSEDE/DELETE 与回滚恢复。
- desktop 前端 tauri-client 改为静态导入 `@tauri-apps/api`，通过 `__TAURI_INTERNALS__` 检测守卫调用，减少 Tauri API dynamic import 构建告警。

## 桌面页面（Stage1）

- Chat：会话切换、输入发送、事件流 inspector、engine turn 回答展示。
- Tasks：创建/编辑/启停/立即运行、状态与错误展示。
- Dimsums：真实列表与启停。
- Memory：检索、timeline、详情按需加载、版本列表查询、可选版本回滚。
- Settings：Gateway 启停、LAN 切换、配对 token、语言切换。

## 远程使用最佳实践（强约束）

- 默认绑定 `127.0.0.1`。
- 用户显式开启“允许局域网”后才绑定 `0.0.0.0`。
- 文档与 UI 提示：远程优先 Tailscale/tunnel，不裸露公网。

## Stage 1 -> Stage 2 主要缺口

- provider/tool calling 已补到 `provider.delta + tool_call 解析`，仍需继续完善“流式中途工具调用/并发 tool calls”细节。
- process runner 观测已补 `pid + started/finished` 与失败元数据，仍需继续补齐子进程树级别采样。
- memory rollback 已具备冲突恢复 + 1200 条压力回归，仍需继续补充更复杂演化策略评测（语义冲突与长期漂移）。
- desktop e2e 仍是「Tauri mock + 真后端链路」混合模式；虽已新增 Rust 侧真后端回归，但浏览器侧真后端矩阵仍需提升。
- 构建层 dynamic import 告警已明显收敛，仍需持续跟进剩余 chunk 噪音。
