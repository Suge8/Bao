use bao_storage::Storage;

#[test]
fn fetch_due_tasks_returns_enabled_tasks() {
    let dir = tempfile::tempdir().expect("tempdir");
    let sqlite_path = dir.path().join("bao.sqlite");

    // Initialize schema.
    let conn = rusqlite::Connection::open(&sqlite_path).expect("open sqlite");
    const INIT_SQL: &str = include_str!("../migrations/0001_init.sql");
    conn.execute_batch(INIT_SQL).expect("init schema");

    let storage = Storage::open(sqlite_path.to_string_lossy().to_string()).expect("open storage");

    // Insert a due task (next_run_at <= now).
    conn.execute(
        "INSERT INTO tasks(task_id, title, enabled, schedule_kind, run_at_ts, interval_ms, cron, timezone, next_run_at, last_run_at, last_status, last_error, tool_dimsum_id, tool_name, tool_args_json, policy_json, kill_switch_group, created_at, updated_at) \
         VALUES (?1, ?2, 1, 'once', ?3, NULL, NULL, NULL, ?3, NULL, NULL, NULL, ?4, ?5, '{}', NULL, NULL, ?3, ?3)",
        rusqlite::params!["t1", "Test", 10_i64, "d1", "noop"],
    )
    .expect("insert task");

    let due = storage.fetch_due_tasks(10, 10).expect("fetch due");
    assert_eq!(due.len(), 1);
    assert_eq!(due[0].id, "t1");
}
