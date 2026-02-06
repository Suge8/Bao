# Bao — PRD（Stage 2 可用基线）

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

## Stage 2 收口结果（当前）

- provider/tool calling：`runEngineTurn` 非工具分支已支持 provider 返回 `tool_call` 与 `tool_calls`，并在回合同步执行（并发批量工具调用 + 轮次上限保护）。
- process runner 观测：`ProcessToolRunner` 已新增 `processTree` 采样（root pid、descendant count、rss/cpu 汇总）并覆盖成功/失败元数据。
- memory 演化：`memory.extract` 新增偏好语义冲突策略（like/dislike 归并到稳定 memory id），降低长期漂移与重复写入。
- 发布门禁：`P0.CORE_SLO` 已改为 fail-closed（缺失观测直接 fail），避免性能证据缺口被误判为通过。
- 回归覆盖：desktop Rust 真后端测试矩阵已扩展 provider 单工具/并发工具调用链路可观测性断言。

## v1.0 发布收口（Go/No-Go 条件）

在进入 Stage 2 前，必须满足以下 v1.0 发布门禁：

1. **P0 Gates 全绿**：`P0.LINT`, `P0.TEST`, `P0.TEST_E2E`, `P0.CARGO_WORKSPACE` 必须 status=pass。
2. **证据齐全**：所有 P0 门禁指定的 `evidence` 文件必须真实存在且内容合法。
3. **审计链完整**：`verify_audit_chain` 验证通过，无 hash 断裂或篡改。
4. **性能/稳定达标**：Flake 率 <= 阈值，核心 SLO（Router/FTS/Scheduler）无超标。
5. **发布收口校验**：`scripts/release-checklist-validate.mjs` 运行通过，生成最终 RC 归档证据。
