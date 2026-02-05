use bao_storage::Storage;

fn setup_db() -> (tempfile::TempDir, String, rusqlite::Connection) {
    let dir = tempfile::tempdir().expect("tempdir");
    let sqlite_path = dir.path().join("bao.sqlite");

    let conn = rusqlite::Connection::open(&sqlite_path).expect("open sqlite");
    const INIT_SQL: &str = include_str!("../migrations/0001_init.sql");
    conn.execute_batch(INIT_SQL).expect("init schema");

    (dir, sqlite_path.to_string_lossy().to_string(), conn)
}

#[test]
fn mark_task_run_disables_once_task_and_clears_next_run() {
    let (_dir, sqlite_path, conn) = setup_db();
    conn.execute(
        "INSERT INTO tasks(task_id, title, enabled, schedule_kind, run_at_ts, interval_ms, cron, timezone, next_run_at, last_run_at, last_status, last_error, tool_dimsum_id, tool_name, tool_args_json, policy_json, kill_switch_group, created_at, updated_at) \
         VALUES (?1, ?2, 1, 'once', ?3, NULL, NULL, NULL, ?3, NULL, NULL, NULL, ?4, ?5, '{}', NULL, NULL, ?3, ?3)",
        rusqlite::params!["t_once", "Once", 10_i64, "d1", "noop"],
    )
    .expect("insert task");

    let storage = Storage::open(sqlite_path).expect("open storage");
    storage.mark_task_run("t_once", "success", None, 10).expect("mark run");

    let (enabled, next_run_at): (i64, Option<i64>) = conn
        .query_row(
            "SELECT enabled, next_run_at FROM tasks WHERE task_id=?1",
            rusqlite::params!["t_once"],
            |r| Ok((r.get(0)?, r.get(1)?)),
        )
        .expect("select");

    assert_eq!(enabled, 0);
    assert!(next_run_at.is_none());
}

#[test]
fn mark_task_run_advances_interval_next_run() {
    let (_dir, sqlite_path, conn) = setup_db();
    conn.execute(
        "INSERT INTO tasks(task_id, title, enabled, schedule_kind, run_at_ts, interval_ms, cron, timezone, next_run_at, last_run_at, last_status, last_error, tool_dimsum_id, tool_name, tool_args_json, policy_json, kill_switch_group, created_at, updated_at) \
         VALUES (?1, ?2, 1, 'interval', NULL, ?3, NULL, NULL, ?4, NULL, NULL, NULL, ?5, ?6, '{}', NULL, NULL, ?4, ?4)",
        rusqlite::params!["t_interval", "Interval", 5_000_i64, 10_i64, "d1", "noop"],
    )
    .expect("insert task");

    let storage = Storage::open(sqlite_path).expect("open storage");
    storage
        .mark_task_run("t_interval", "success", None, 10)
        .expect("mark run");

    let next_run_at: Option<i64> = conn
        .query_row(
            "SELECT next_run_at FROM tasks WHERE task_id=?1",
            rusqlite::params!["t_interval"],
            |r| r.get(0),
        )
        .expect("select");

    assert_eq!(next_run_at, Some(15));
}

#[test]
fn mark_task_run_advances_cron_next_run() {
    let (_dir, sqlite_path, conn) = setup_db();
    conn.execute(
        "INSERT INTO tasks(task_id, title, enabled, schedule_kind, run_at_ts, interval_ms, cron, timezone, next_run_at, last_run_at, last_status, last_error, tool_dimsum_id, tool_name, tool_args_json, policy_json, kill_switch_group, created_at, updated_at) \
         VALUES (?1, ?2, 1, 'cron', NULL, NULL, ?3, NULL, ?4, NULL, NULL, NULL, ?5, ?6, '{}', NULL, NULL, ?4, ?4)",
        rusqlite::params!["t_cron", "Cron", "0 * * * * *", 10_i64, "d1", "noop"],
    )
    .expect("insert task");

    let storage = Storage::open(sqlite_path).expect("open storage");
    storage
        .mark_task_run("t_cron", "success", None, 10)
        .expect("mark run");

    let next_run_at: Option<i64> = conn
        .query_row(
            "SELECT next_run_at FROM tasks WHERE task_id=?1",
            rusqlite::params!["t_cron"],
            |r| r.get(0),
        )
        .expect("select");

    assert_eq!(next_run_at, Some(60));
}

#[test]
fn mark_task_run_advances_cron_with_timezone() {
    let (_dir, sqlite_path, conn) = setup_db();
    conn.execute(
        "INSERT INTO tasks(task_id, title, enabled, schedule_kind, run_at_ts, interval_ms, cron, timezone, next_run_at, last_run_at, last_status, last_error, tool_dimsum_id, tool_name, tool_args_json, policy_json, kill_switch_group, created_at, updated_at) \
         VALUES (?1, ?2, 1, 'cron', NULL, NULL, ?3, ?4, ?5, NULL, NULL, NULL, ?6, ?7, '{}', NULL, NULL, ?5, ?5)",
        rusqlite::params![
            "t_cron_tz",
            "Cron TZ",
            "0 0 * * * *",
            "Asia/Shanghai",
            0_i64,
            "d1",
            "noop"
        ],
    )
    .expect("insert task");

    let storage = Storage::open(sqlite_path).expect("open storage");
    storage
        .mark_task_run("t_cron_tz", "success", None, 0)
        .expect("mark run");

    let next_run_at: Option<i64> = conn
        .query_row(
            "SELECT next_run_at FROM tasks WHERE task_id=?1",
            rusqlite::params!["t_cron_tz"],
            |r| r.get(0),
        )
        .expect("select");

    assert_eq!(next_run_at, Some(3_600));
}
