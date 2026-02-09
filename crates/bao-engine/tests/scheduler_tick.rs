use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::Arc;
use std::time::Duration;

use bao_engine::scheduler::{CrashInjector, CrashPoint, SchedulerService};
use bao_engine::storage::SqliteStorage;
use bao_plugin_host::{PluginHostError, ToolRunResult, ToolRunner};
use bao_storage::Storage;
use rusqlite::{params, Connection};

const INIT_SQL: &str = include_str!("../../bao-storage/migrations/0001_init.sql");

#[test]
fn tick_runs_due_task_and_writes_events_and_audit() {
    let dir = tempfile::tempdir().expect("tempdir");
    let db = dir.path().join("test.sqlite");
    let conn = Connection::open(&db).expect("open");
    conn.execute_batch(INIT_SQL).expect("init schema");

    insert_once_task(&conn, "t1", "task", None);

    let storage = Arc::new(Storage::open(db.to_string_lossy().to_string()).expect("storage"));
    let scheduler = SchedulerService::new(
        Arc::new(SqliteStorage::new(storage.clone())),
        Arc::new(TestRunner::ok()),
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

#[test]
fn tick_writes_task_reminder_into_default_session() {
    let dir = tempfile::tempdir().expect("tempdir");
    let db = dir.path().join("task_reminder.sqlite");
    let conn = Connection::open(&db).expect("open");
    conn.execute_batch(INIT_SQL).expect("init schema");

    seed_default_session(&conn);
    insert_once_task(&conn, "t1", "叫我喝水", None);

    let storage = Arc::new(Storage::open(db.to_string_lossy().to_string()).expect("storage"));
    let scheduler = SchedulerService::new(
        Arc::new(SqliteStorage::new(storage.clone())),
        Arc::new(TestRunner::ok()),
    );

    scheduler.tick(10);

    let reminder_count: i64 = conn
        .query_row(
            "SELECT COUNT(1) FROM messages WHERE session_id='default' AND role='assistant' AND content LIKE '%[任务提醒]%'",
            [],
            |r| r.get(0),
        )
        .expect("reminder count");
    assert_eq!(reminder_count, 1);
}

#[test]
fn run_task_now_blocks_unauthorized_tool_before_execution() {
    let dir = tempfile::tempdir().expect("tempdir");
    let db = dir.path().join("unauth.sqlite");
    let conn = Connection::open(&db).expect("open");
    conn.execute_batch(INIT_SQL).expect("init schema");

    let manifest = serde_json::json!({
        "tools": [
            {"name": "t1", "permissions": ["cmd.exec"]}
        ]
    });
    conn.execute(
        "INSERT INTO dimsums(dimsum_id, enabled, channel, version, manifest_json, installed_at, updated_at) VALUES (?1, 1, 'community', '0.1.0', ?2, 0, 0)",
        params!["d1", manifest.to_string()],
    )
    .expect("insert dimsum");
    conn.execute(
        "INSERT INTO settings(key, value_json, updated_at) VALUES (?1, ?2, 0)",
        params![
            "permissions.capabilities",
            serde_json::json!({"cmd.exec": false}).to_string()
        ],
    )
    .expect("insert settings");

    insert_once_task(&conn, "t1", "task", None);

    let storage = Arc::new(Storage::open(db.to_string_lossy().to_string()).expect("storage"));
    let runner = Arc::new(TestRunner::ok());
    let scheduler = SchedulerService::new(
        Arc::new(SqliteStorage::new(storage.clone())),
        runner.clone(),
    );

    scheduler.run_task_now("t1", 10);
    assert_eq!(runner.calls(), 0);

    let rejected_count: i64 = conn
        .query_row(
            "SELECT COUNT(1) FROM events WHERE type='task.run.rejected'",
            [],
            |r| r.get(0),
        )
        .expect("rejected events count");
    assert_eq!(rejected_count, 1);

    let audit_count: i64 = conn
        .query_row(
            "SELECT COUNT(1) FROM audit_events WHERE action='task.run.rejected'",
            [],
            |r| r.get(0),
        )
        .expect("rejected audit count");
    assert_eq!(audit_count, 1);
}

#[test]
fn capability_revocation_stops_running_group_fail_closed() {
    let dir = tempfile::tempdir().expect("tempdir");
    let db = dir.path().join("revoke.sqlite");
    let conn = Connection::open(&db).expect("open");
    conn.execute_batch(INIT_SQL).expect("init schema");

    let manifest = serde_json::json!({
        "tools": [
            {"name": "t1", "permissions": ["cmd.exec"]}
        ]
    });
    conn.execute(
        "INSERT INTO dimsums(dimsum_id, enabled, channel, version, manifest_json, installed_at, updated_at) VALUES (?1, 1, 'community', '0.1.0', ?2, 0, 0)",
        params!["d1", manifest.to_string()],
    )
    .expect("insert dimsum");
    conn.execute(
        "INSERT INTO settings(key, value_json, updated_at) VALUES (?1, ?2, 0)",
        params![
            "permissions.capabilities",
            serde_json::json!({"cmd.exec": true}).to_string()
        ],
    )
    .expect("insert settings");

    insert_once_task(&conn, "t1", "task", Some("g1"));

    let storage = Arc::new(Storage::open(db.to_string_lossy().to_string()).expect("storage"));
    let runner = Arc::new(TestRunner::blocking());
    let scheduler = Arc::new(SchedulerService::new(
        Arc::new(SqliteStorage::new(storage.clone())),
        runner.clone(),
    ));

    let scheduler_for_run = scheduler.clone();
    let jh = std::thread::spawn(move || {
        scheduler_for_run.run_task_now("t1", 10);
    });

    std::thread::sleep(Duration::from_millis(50));
    conn.execute(
        "UPDATE settings SET value_json=?2, updated_at=11 WHERE key=?1",
        params![
            "permissions.capabilities",
            serde_json::json!({"cmd.exec": false}).to_string()
        ],
    )
    .expect("revoke capability");

    scheduler.enforce_capability_gate(11);
    jh.join().expect("run thread joins");

    assert!(runner.kill_called());

    let revoked_count: i64 = conn
        .query_row(
            "SELECT COUNT(1) FROM events WHERE type='task.run.revoked'",
            [],
            |r| r.get(0),
        )
        .expect("revoked events count");
    assert_eq!(revoked_count, 1);

    let revoked_audit_count: i64 = conn
        .query_row(
            "SELECT COUNT(1) FROM audit_events WHERE action='task.run.revoked'",
            [],
            |r| r.get(0),
        )
        .expect("revoked audit count");
    assert_eq!(revoked_audit_count, 1);
}

#[test]
fn crash_during_run_recovers_with_contiguous_replay_and_at_least_once() {
    let dir = tempfile::tempdir().expect("tempdir");
    let db = dir.path().join("crash_recover.sqlite");
    let conn = Connection::open(&db).expect("open");
    conn.execute_batch(INIT_SQL).expect("init schema");

    insert_once_task(&conn, "t1", "task", None);

    let first_storage = Arc::new(Storage::open(db.to_string_lossy().to_string()).expect("storage"));
    let first_scheduler = SchedulerService::new(
        Arc::new(SqliteStorage::new(first_storage.clone())),
        Arc::new(TestRunner::ok()),
    )
    .with_crash_injector(Arc::new(OneShotCrashInjector::new(
        CrashPoint::AfterTaskStartedEvent,
    )));

    let crashed = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        first_scheduler.tick(10);
    }));
    assert!(
        crashed.is_err(),
        "expected injected crash before task completion"
    );

    let second_storage =
        Arc::new(Storage::open(db.to_string_lossy().to_string()).expect("storage"));
    let second_runner = Arc::new(TestRunner::ok());
    let second_scheduler = SchedulerService::new(
        Arc::new(SqliteStorage::new(second_storage.clone())),
        second_runner.clone(),
    );
    second_scheduler.tick(11);

    let started_count: i64 = conn
        .query_row(
            "SELECT COUNT(1) FROM events WHERE type='task.run.started'",
            [],
            |r| r.get(0),
        )
        .expect("started count");
    let finished_count: i64 = conn
        .query_row(
            "SELECT COUNT(1) FROM events WHERE type='task.run.finished'",
            [],
            |r| r.get(0),
        )
        .expect("finished count");
    assert_eq!(
        started_count, 2,
        "at-least-once requires restart re-run after crash"
    );
    assert_eq!(finished_count, 1, "only recovered run should finish");
    assert_eq!(
        second_runner.calls(),
        1,
        "tool is executed exactly once after restart"
    );

    let task_row: (i64, Option<String>) = conn
        .query_row(
            "SELECT enabled, last_status FROM tasks WHERE task_id='t1'",
            [],
            |r| Ok((r.get(0)?, r.get(1)?)),
        )
        .expect("task state");
    assert_eq!(
        task_row.0, 0,
        "once task must be disabled after successful recovery"
    );
    assert_eq!(task_row.1.as_deref(), Some("success"));

    let mut stmt = conn
        .prepare("SELECT eventId FROM events ORDER BY eventId ASC")
        .expect("prepare event ids");
    let event_ids = stmt
        .query_map([], |r| r.get::<_, i64>(0))
        .expect("query event ids")
        .collect::<Result<Vec<_>, _>>()
        .expect("collect event ids");
    assert!(
        !event_ids.is_empty(),
        "events should exist after crash + recovery"
    );
    for pair in event_ids.windows(2) {
        assert_eq!(
            pair[1],
            pair[0] + 1,
            "event replay cursor must remain contiguous"
        );
    }

    let audit = second_storage
        .verify_audit_chain()
        .expect("verify audit chain");
    assert!(audit.ok, "audit chain must stay valid after crash recovery");
}

struct TestRunner {
    mode: RunnerMode,
    calls: AtomicUsize,
    kill_called: AtomicBool,
}

enum RunnerMode {
    Ok,
    Blocking,
}

impl TestRunner {
    fn ok() -> Self {
        Self {
            mode: RunnerMode::Ok,
            calls: AtomicUsize::new(0),
            kill_called: AtomicBool::new(false),
        }
    }

    fn blocking() -> Self {
        Self {
            mode: RunnerMode::Blocking,
            calls: AtomicUsize::new(0),
            kill_called: AtomicBool::new(false),
        }
    }

    fn calls(&self) -> usize {
        self.calls.load(Ordering::SeqCst)
    }

    fn kill_called(&self) -> bool {
        self.kill_called.load(Ordering::SeqCst)
    }
}

impl ToolRunner for TestRunner {
    fn run_tool(
        &self,
        _dimsum_id: &str,
        _tool_name: &str,
        _args: &serde_json::Value,
    ) -> Result<ToolRunResult, PluginHostError> {
        self.calls.fetch_add(1, Ordering::SeqCst);
        match self.mode {
            RunnerMode::Ok => Ok(ToolRunResult {
                ok: true,
                output: serde_json::json!({"ok": true}),
            }),
            RunnerMode::Blocking => {
                while !self.kill_called.load(Ordering::SeqCst) {
                    std::thread::sleep(Duration::from_millis(5));
                }
                Err(PluginHostError {
                    code: "KILLED".to_string(),
                    message: "killed by test".to_string(),
                    metadata: None,
                })
            }
        }
    }

    fn kill_group(&self, _group: &str) {
        self.kill_called.store(true, Ordering::SeqCst);
    }
}

struct OneShotCrashInjector {
    point: CrashPoint,
    fired: AtomicBool,
}

impl OneShotCrashInjector {
    fn new(point: CrashPoint) -> Self {
        Self {
            point,
            fired: AtomicBool::new(false),
        }
    }
}

impl CrashInjector for OneShotCrashInjector {
    fn should_crash(&self, point: CrashPoint, _task_id: &str) -> bool {
        point == self.point && !self.fired.swap(true, Ordering::SeqCst)
    }
}

fn seed_default_session(conn: &Connection) {
    conn.execute(
        "INSERT INTO sessions(session_id, title, created_at, updated_at) VALUES ('default', 'Default Session', 0, 0)",
        [],
    )
    .expect("seed default session");
}

fn insert_once_task(conn: &Connection, task_id: &str, title: &str, group: Option<&str>) {
    let tool_args = serde_json::json!({"k": "v"}).to_string();
    conn.execute(
        "INSERT INTO tasks(task_id, title, enabled, schedule_kind, run_at_ts, interval_ms, cron, timezone, next_run_at, last_run_at, last_status, last_error, tool_dimsum_id, tool_name, tool_args_json, policy_json, kill_switch_group, created_at, updated_at) \
         VALUES (?1, ?2, 1, 'once', 0, NULL, NULL, NULL, 1, NULL, NULL, NULL, 'd1', 't1', ?3, NULL, ?4, 0, 0)",
        params![task_id, title, tool_args, group],
    )
    .expect("insert task");
}
