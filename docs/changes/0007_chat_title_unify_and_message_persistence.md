[FIX] 2026-02-09 对话标题统一与消息即时持久化（local）

## 当前进度

- 已完成：统一桌面会话显示标题，清理“默认对话 / 新对话+时间 / 新对话 1,2”混用。
- 已完成：会话列表时间信息改为小字号并放在会话项右下角。
- 已完成：补齐 user/assistant 消息入库与按会话历史读取链路。

## 改动记录（最近）

- `apps/desktop/src/lib/session-titles.ts`：
  - 系统会话标题统一展示为基础标签（如“新对话”），不再显示旧的随机会话 ID 时间后缀。
  - 兼容历史系统标题（`Default Session/default/默认对话/与 sessionId 相同/编号系统标题`）并统一收敛展示。
- `apps/desktop/src/pages/chat/layout.tsx`：
  - 会话列表项增加右下角小字号时间（`updatedAt` 优先，回退 `createdAt`）。
  - 增加按 `activeSessionId` 拉取历史消息逻辑，避免仅依赖实时事件导致刷新丢上下文。
- `apps/desktop/src/data/client.ts`、`apps/desktop/src/data/tauri-client.ts`：
  - 扩展 `listSessions` 返回 `createdAt/updatedAt`。
  - 新增 `listMessages(sessionId, limit)` 桌面客户端接口与 Tauri 调用。
- `apps/desktop/src-tauri/src/lib.rs`、`crates/bao-gateway/src/lib.rs`：
  - 新增 `listMessages` IPC 命令与网关 `list_messages` 读取实现。
  - `send_message`/移动端 `SendMessage` 路径改为先写 `messages` 表再写 `events`。
  - `run_engine_turn` 在产出 assistant 文本后先写 `messages` 表，再发 `engine.turn` 事件。
- `apps/desktop/tests/e2e/fixtures/rust-simulator.ts`：
  - 补齐 `list_messages` 模拟命令与会话/消息时间字段，保持桌面端 E2E 兼容。

## 未来发展（优先级）

1. 高：补充对话历史持久化回归测试（重启后消息一致性、会话切换历史回放）。
2. 中：为会话标题引入“用户重命名”状态位，避免用户自定义标题被系统收敛规则误判。
3. 中：评估将 `messages.list` 事件从日志流中降噪（仅调试模式记录），减少事件表噪声。
