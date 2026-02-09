[FEAT] 2026-02-09 任务执行结果默认写入主对话提醒（local）

## 当前进度

- 已完成：任务执行成功/失败后，自动在默认主对话写入一条 assistant 提醒消息。
- 已完成：失败场景（权限不足/被撤销/执行失败）同样写入会话提醒，避免仅看到 completed 却无上下文。
- 已完成：新增回归测试，验证任务执行后会在 `default` 会话生成提醒消息。
- 已完成：对本次实现执行 code-simplifier 行为等价重构，减少重复逻辑并提升可维护性。

## 改动记录（最近）

- `crates/bao-storage/src/lib.rs`：
  - 新增 `ensure_session_exists` 与 `append_message` 存储能力，用于保证会话存在并写入消息。
  - 提炼 `parse_task_record`，复用任务记录解析逻辑。
- `crates/bao-engine/src/storage.rs`：
  - 扩展 `StorageFacade`，暴露会话保证与消息追加接口给 Scheduler 使用。
- `crates/bao-engine/src/scheduler.rs`：
  - 增加默认会话常量（`default` / `Default Session`）。
  - 任务完成（成功/失败）后写入 `[任务提醒]` 会话消息，并落 `message.send` 事件。
  - 权限拒绝/权限撤销场景也写入会话提醒。
  - 提炼 `emit_task_action` 与提醒文案拼装，减少事件写入和字符串构造重复。
- `crates/bao-engine/tests/scheduler_tick.rs`：
  - 新增 `tick_writes_task_reminder_into_default_session` 用例。
  - 提炼测试辅助函数，减少重复 SQL 片段。

## 未来发展（优先级）

1. 高：在任务卡片中增加“跳转主对话查看提醒”入口，缩短定位路径。
2. 中：将提醒文案做 i18n 与结构化模板（含任务 ID / 运行时间 / 关键输出摘要）。
3. 中：为提醒策略增加设置项（仅失败提醒 / 全部提醒 / 静默模式）。
