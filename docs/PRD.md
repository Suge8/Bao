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

- provider/tool calling 协议覆盖度继续提升（复杂 tool-calling 与流式细节）。
- process runner 已支持 stdout/stderr 回传与 kill-group 中断；后续补齐更细粒度进程树观测。
- memory rollback 已支持版本列表查询与冲突场景恢复；后续补强大规模数据下的演化策略与评测。
- desktop e2e 目前主要为 Tauri mock 驱动；Stage2 需补齐“真后端链路”端到端测试矩阵。
- 构建层仍存在 Tauri API dynamic import 警告；Stage2 需收敛 chunk 策略，降低构建噪音。
