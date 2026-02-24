---
name: cron
description: Schedule reminders and recurring tasks.
---

# Cron

Use the `cron` tool to schedule reminders or recurring tasks.

## Three Modes

1. **Reminder** - message is sent directly to user
2. **Task** - message is a task description, agent executes and sends result
3. **One-time** - runs once at a specific time, then auto-deletes

## Examples

Fixed reminder:
```
cron(action="add", message="Time to take a break!", every_seconds=1200)
```

Dynamic task (agent executes each time):
```
cron(action="add", message="Check Suge8/bao GitHub stars and report", every_seconds=600)
```

One-time scheduled task (compute ISO datetime from current time):
```
cron(action="add", message="Remind me about the meeting", at="<ISO datetime>")
```

Timezone-aware cron:
```
cron(action="add", message="Morning standup", cron_expr="0 9 * * 1-5", tz="America/Vancouver")
```

List/remove:
```
cron(action="list")
cron(action="remove", job_id="abc123")
```

## Time Expressions

| User says | Parameters |
|-----------|------------|
| every 20 minutes | every_seconds: 1200 |
| every hour | every_seconds: 3600 |
| every day at 8am | cron_expr: "0 8 * * *" |
| weekdays at 5pm | cron_expr: "0 17 * * 1-5" |
| 9am Vancouver time daily | cron_expr: "0 9 * * *", tz: "America/Vancouver" |
| at a specific time | at: ISO datetime string (compute from current time) |

## Timezone

Use `tz` with `cron_expr` to schedule in a specific IANA timezone. Without `tz`, the server's local timezone is used.

## 中文示例 / Chinese Examples

固定提醒（每 20 分钟休息一次）：
```
cron(action="add", message="该休息一下了！", every_seconds=1200)
```

每天早上 8 点提醒：
```
cron(action="add", message="早安！检查今日待办事项。", cron_expr="0 8 * * *")
```

工作日下午 6 点提醒下班：
```
cron(action="add", message="下班啦！记得关闭工作应用。", cron_expr="0 18 * * 1-5")
```

定时执行任务（agent 执行并回报）：
```
cron(action="add", message="检查 GitHub 新 issue 并汇报", every_seconds=3600)
```

北京时间每天 9 点：
```
cron(action="add", message="早间日报", cron_expr="0 9 * * *", tz="Asia/Shanghai")
```

## 中文口语 → 参数映射

| 用户说 | 参数 |
|--------|------|
| 每 20 分钟 | every_seconds: 1200 |
| 每小时 | every_seconds: 3600 |
| 每天早上 8 点 | cron_expr: "0 8 * * *" |
| 工作日下午 5 点 | cron_expr: "0 17 * * 1-5" |
| 每天北京时间 9 点 | cron_expr: "0 9 * * *", tz: "Asia/Shanghai" |
| 指定某个时刻 | at: ISO datetime 字符串（从当前时间计算） |

## 重要：Agent 使用 cron 工具，而非终端命令

- ✅ 正确：调用 `cron` 工具（`action="add"` 等）
- ❌ 错误：用 `exec` 工具运行 `bao cron add ...`（这是给终端用户的 CLI 命令，不是 agent 的工具调用）
