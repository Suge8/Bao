# Desktop Integrator Wiring Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 把 `crates/bao-engine` / `crates/bao-plugin-host` / `crates/bao-storage` / `crates/bao-gateway` 与 `apps/desktop/src-tauri` 彻底接线跑通：Tauri IPC 命令、`bao:event` 实时渲染、scheduler tick + 到期任务触发 tool + audit/events、Kill Switch、远程使用最佳实践，并保证 `pnpm test` / `pnpm test:e2e` / `cargo test` 全绿且文档补全。

**Architecture:**
- `apps/desktop/src-tauri` 作为唯一桌面 Gateway：通过 Tauri commands 暴露能力给前端；通过 `bao:event` Tauri event 将 SQLite events tail 到 UI。
- `crates/bao-gateway` 继续负责“移动端连接 + 事件回放 + 一期 minimal IPC helper”；桌面端复用同一 SQLite（Single Source of Truth）。
- `crates/bao-engine` 提供 scheduler tick + task runner；`crates/bao-plugin-host` 执行 dimsum tools（本期可 stub 最小可执行路径，但必须支持 kill）。

**Tech Stack:** Rust (Tauri, tokio, rusqlite), React/Vite (desktop UI), pnpm, cargo.

---

## 0. Preflight（只读确认）

### Task 0: 读取现有实现并列缺口

**Files:**
- Read: `apps/desktop/src-tauri/src/lib.rs`
- Read: `crates/bao-gateway/src/lib.rs`
- Read: `crates/bao-engine/**`
- Read: `crates/bao-storage/**`
- Read: `crates/bao-plugin-host/**`
- Read: `apps/desktop/src/**`（确认哪些 UI 入口已存在）
- Read: `docs/PRD.md`, `docs/AGENTS.md`

**Step 1: 找到 UI 需要的 IPC 列表**
Run: `rg -n "invoke\(|tauri\.invoke|listSessions|listTasks|gateway" apps/desktop/src -S`
Expected: 输出 UI 调用点；记录哪些 commands 必须接通。

**Step 2: 找到 gateway/engine/storage/plugin-host 的真实能力边界**
Run: `rg -n "pub fn|pub async fn" crates/bao-(gateway|engine|storage|plugin-host)/src -S`
Expected: 列出可复用 API；标记缺失：tasks/memory/scheduler/kill。

---

## 1. Tauri Commands 完整接线

### Task 1: 为 tasks/memory 增加 gateway_handle API（最小可用）

**Files:**
- Modify: `crates/bao-gateway/src/lib.rs`
- Modify: `crates/bao-storage/src/**`（若 gateway 需要调用 storage API 而不是直连 rusqlite）
- Test: `crates/bao-gateway/src/lib.rs`（现有 tests 区）

**Step 1: 写失败测试（gateway handle tasks/memory）**
- 增加单测：调用 `GatewayHandle::{create_task, update_task, enable_task, disable_task, run_task_now}` 以及 `search_index/get_items/get_timeline/apply_mutation_plan/rollback_version`（这些 API 若不存在先写占位，测试会 fail）。

**Step 2: 运行测试确认失败**
Run: `cargo test -p bao-gateway -q`
Expected: FAIL（missing method / unimplemented）。

**Step 3: 实现最小逻辑**
- tasks：先落到 SQLite 的 `tasks` 表（或已有 schema），并 append 对应 `BaoEventV1` 到 `events`。
- memory：先落到 SQLite 的 `memory_items/memory_versions/memory_links`（按 PRD V1），提供最小查询/回滚/plan apply。
- 每个操作必须写 `audit_log/audit_events`（若现表名不同，按现实现接入）。

**Step 4: 运行测试**
Run: `cargo test -p bao-gateway -q`
Expected: PASS。

### Task 2: 桌面端新增/补全 Tauri commands

**Files:**
- Modify: `apps/desktop/src-tauri/src/lib.rs`
- Modify: `apps/desktop/src/**`（如需要更新 invoke 名字对齐）

**Step 1: 写失败 UI E2E/单测（若已有测试框架）**
Run: `pnpm -C apps/desktop test -q || true`
Expected: 如果已有：新增针对 commands 的覆盖；如果没有：后续 Task 8 补。

**Step 2: 增加 commands 并接到 gateway_handle**
- `createTask/updateTask/enableTask/disableTask/runTaskNow`
- `searchIndex/getItems/getTimeline/applyMutationPlan/rollbackVersion`
- 统一返回 `BaoEventV1` 或明确的结构（与 UI 期望一致）。

**Step 3: 确认 commands 注册到 `invoke_handler![]`**
Run: `rg -n "generate_handler" apps/desktop/src-tauri/src/lib.rs -n`
Expected: 新 commands 在 handler 列表里。

---

## 2. `bao:event` 实时渲染

### Task 3: UI 订阅 `bao:event` 并驱动渲染

**Files:**
- Modify: `apps/desktop/src/**`（监听 tauri event）
- Test: `apps/desktop/e2e/**`（若存在）

**Step 1: 写失败 E2E（事件到 UI）**
- 启动桌面后触发一个 IPC（如 `listSessions`），断言 UI 列表变更（来自 `bao:event` 而非 invoke 返回）。

**Step 2: 实现订阅**
- 前端：`listen("bao:event", handler)`，将 `BaoEventV1` feed 到 store。

**Step 3: 跑 E2E**
Run: `pnpm -C apps/desktop test:e2e`
Expected: PASS。

---

## 3. Scheduler/心跳 + 到期任务触发 tool + audit/events

### Task 4: 替换 phase1 heartbeat，接入 engine scheduler tick

**Files:**
- Modify: `apps/desktop/src-tauri/src/lib.rs`
- Modify: `crates/bao-engine/src/**`
- Modify: `crates/bao-plugin-host/src/**`
- Modify: `crates/bao-storage/src/**`
- Test: `crates/bao-engine/tests/**`（若无则新增）

**Step 1: 写失败单测（tick 能捞到到期任务并执行）**
- 构造：插入一个到期任务，tick 一次，断言：
  - tool 被调用（通过 plugin-host stub 记录）
  - `events` 追加 `task.run.started`/`task.run.finished`
  - `audit` 追加链。

**Step 2: 实现 scheduler tick**
- 桌面启动时 `tokio::spawn` 一个 `interval(Duration::from_secs(1..5))` tick。
- tick：从 storage 查询 due tasks → 通过 engine 生成 toolcall → plugin-host 执行 → 写 events/audit。

**Step 3: Kill Switch**
- 在桌面 state 里维护“正在运行的 task/tool” JoinHandle/CancelToken。
- `killSwitchStopAll`：取消所有正在运行的 tool/task + 停 gateway + 停 scheduler。

**Step 4: 运行 Rust tests**
Run: `cargo test -q`
Expected: PASS。

---

## 4. 远程使用最佳实践（默认仅本机）

### Task 5: 网关绑定与 UI/文档提示

**Files:**
- Modify: `apps/desktop/src-tauri/src/lib.rs`
- Modify: `apps/desktop/src/**`（设置页提示）
- Modify: `docs/PRD.md`
- Modify: `docs/AGENTS.md`

**Step 1: 写测试（allowLan 影响下一次 start bind）**
Run: `cargo test -p bao-gateway -q`
Expected: 增加覆盖：allowLan=false 时 bind=127.0.0.1；true 时 bind=0.0.0.0。

**Step 2: UI 提示**
- 明确：远程请用 Tailscale/tunnel；不要裸露公网。

---

## 5. 全量验证

### Task 6: 补齐缺失的单测（按新增能力）

**Files:**
- Modify/Create: `crates/**/tests/**`

**Step 1: 为每条 IPC/行为补一个最小单测**
- tasks/memory/scheduler/kill。

**Step 2: 跑 cargo tests**
Run: `cargo test -q`
Expected: PASS。

### Task 7: 跑前端单测
Run: `pnpm test`
Expected: PASS。

### Task 8: 跑 UI E2E
Run: `pnpm test:e2e`
Expected: PASS。

---

## 6. 文档收尾

### Task 9: 以本计划为基准补全 docs

**Files:**
- Modify: `docs/AGENTS.md`
- Modify: `docs/PRD.md`
- Modify: `docs/changes/**`（按规范记录）

**Step 1: 更新文档**
- 写清 IPC 清单、事件流、scheduler tick、远程最佳实践。

**Step 2: 文档自检**
Run: `rg -n "TODO|TBD" docs/PRD.md docs/AGENTS.md -S || true`
Expected: 无关键 TODO。
