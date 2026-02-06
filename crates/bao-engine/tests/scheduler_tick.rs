use std::sync::Arc;

use bao_engine::scheduler::SchedulerService;
use bao_engine::storage::SqliteStorage;
use bao_plugin_host::process_runner::ProcessToolRunner;
use bao_storage::Storage;
use rusqlite::{params, Connection};

const INIT_SQL: &str = include_str!("../../bao-storage/migrations/0001_init.sql");

#[test]
fn tick_runs_due_task_and_writes_events_and_audit() {
    let dir = tempfile::tempdir().expect("tempdir");
    let db = dir.path().join("test.sqlite");
    let conn = Connection::open(&db).expect("open");
    conn.execute_batch(INIT_SQL).expect("init schema");

    let tool_args = serde_json::json!({"k": "v"}).to_string();
    conn.execute(
        "INSERT INTO tasks(task_id, title, enabled, schedule_kind, run_at_ts, interval_ms, cron, timezone, next_run_at, last_run_at, last_status, last_error, tool_dimsum_id, tool_name, tool_args_json, policy_json, kill_switch_group, created_at, updated_at) \
         VALUES (?1, ?2, 1, 'once', 0, NULL, NULL, NULL, 1, NULL, NULL, NULL, 'd1', 't1', ?3, NULL, NULL, 0, 0)",
        params!["t1", "task", tool_args],
    )
    .expect("insert task");

    let storage = Arc::new(Storage::open(db.to_string_lossy().to_string()).expect("storage"));
    let scheduler = SchedulerService::new(
        Arc::new(SqliteStorage::new(storage.clone())),
        Arc::new(ProcessToolRunner::new()),
    );

    scheduler.tick(10);

    let mut stmt = conn
        .prepare(
            "SELECT COUNT(1) FROM events WHERE type IN ('task.run.started','task.run.finished')",
        )
        .expect("prepare");
    let count: i64 = stmt
        .query_row([], |r: &rusqlite::Row<'_>| r.get(0))
        .expect("count");
    assert!(count >= 2);

    let mut stmt = conn
        .prepare("SELECT COUNT(1) FROM audit_events WHERE action IN ('task.run.started','task.run.finished')")
        .expect("prepare");
    let audit_count: i64 = stmt
        .query_row([], |r: &rusqlite::Row<'_>| r.get(0))
        .expect("audit count");
    assert!(audit_count >= 2);
}
