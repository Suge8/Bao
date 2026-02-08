[FIX] 2026-02-08 对话页移除标题并补齐会话删除能力（local）

## 当前进度

- 已完成：桌面端对话页移除顶部“对话”标题。
- 已完成：左侧会话项新增删除按钮，并接入真实删除链路（前端 -> Tauri -> Gateway -> SQLite）。
- 已完成：右侧“新对话”按钮改为仅 icon 展示。
- 已完成：会话标题改为用户友好命名策略（默认“新对话 N”，并对历史随机串会话做友好展示）。

## 改动记录（最近）

- `apps/desktop/src/pages/chat.tsx`：移除页面顶部标题区域。
- `apps/desktop/src/pages/chat/layout.tsx`：
  - 左侧会话项增加删除按钮（`chat-delete-session-{id}`）。
  - 新增 `deleteSession` 处理逻辑，删除后刷新会话并清理对应消息缓存。
  - 右侧“新对话”按钮改为仅图标（保留 `aria-label/title`）。
  - 新建会话时改为写入用户友好标题（`新对话 N`），侧栏主标题不再直接显示技术 ID。
- `apps/desktop/src/lib/session-titles.ts`：新增会话标题策略工具，统一默认命名与历史随机 ID 的友好展示。
- `apps/desktop/src/data/client.ts`：新增 `deleteSession(sessionId)` 客户端接口。
- `apps/desktop/src/data/tauri-client.ts`：新增 `delete_session` invoke 封装。
- `apps/desktop/src-tauri/src/lib.rs`：新增 `deleteSession` Tauri command 与 `SessionIdInput`。
- `crates/bao-gateway/src/lib.rs`：新增 `delete_session`，删除 `tool_calls/messages/sessions` 并写 `sessions.delete` 事件。
- `apps/desktop/src/i18n/desktop-locales.ts`：新增删除会话文案键。
- `apps/desktop/tests/e2e/fixtures/rust-simulator.ts`：补充 `delete_session` 模拟命令。

## 未来发展（优先级）

1. 高：补充 e2e 用例，验证“删除当前会话后自动切换目标会话”行为。
2. 中：补充删除会话确认交互（避免误删）。
3. 中：评估是否保留或清理该会话历史 `events` 记录的产品策略。
4. 低：为会话标题补充“首条消息自动摘要命名”策略（保留用户手动改名优先级）。
