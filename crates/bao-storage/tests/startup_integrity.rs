use bao_storage::{Storage, StorageError};
use rusqlite::Connection;

const INIT_SQL: &str = include_str!("../migrations/0001_init.sql");

#[test]
fn open_rejects_non_contiguous_event_sequence_with_structured_error() {
    let dir = tempfile::tempdir().expect("tempdir");
    let db = dir.path().join("startup_gap.sqlite");
    let conn = Connection::open(&db).expect("open");
    conn.execute_batch(INIT_SQL).expect("init schema");

    conn.execute(
        "INSERT INTO events(eventId, ts, type, payload_json) VALUES (1, 1, 'x', '{}')",
        [],
    )
    .expect("insert event 1");
    conn.execute(
        "INSERT INTO events(eventId, ts, type, payload_json) VALUES (3, 2, 'x', '{}')",
        [],
    )
    .expect("insert event 3");

    let err = match Storage::open(db.to_string_lossy().to_string()) {
        Ok(_) => panic!("must reject event gap"),
        Err(err) => err,
    };
    match err {
        StorageError::UnsafeState {
            code,
            message: _,
            details,
        } => {
            assert_eq!(code, "EVENT_SEQUENCE_GAP");
            assert_eq!(details["minEventId"], serde_json::json!(1));
            assert_eq!(details["maxEventId"], serde_json::json!(3));
            assert_eq!(details["rowCount"], serde_json::json!(2));
        }
        other => panic!("unexpected error: {other:?}"),
    }
}

#[test]
fn open_rejects_tampered_audit_chain_with_structured_error() {
    let dir = tempfile::tempdir().expect("tempdir");
    let db = dir.path().join("startup_audit.sqlite");
    let conn = Connection::open(&db).expect("open");
    conn.execute_batch(INIT_SQL).expect("init schema");

    let storage =
        Storage::open_unchecked(db.to_string_lossy().to_string()).expect("unchecked open");
    storage
        .insert_audit_event(
            1,
            "task.run.started",
            "task",
            "t1",
            &serde_json::json!({"x":1}),
        )
        .expect("insert audit 1");
    storage
        .insert_audit_event(
            2,
            "task.run.finished",
            "task",
            "t1",
            &serde_json::json!({"x":2}),
        )
        .expect("insert audit 2");

    conn.execute("UPDATE audit_events SET hash='deadbeef' WHERE id=2", [])
        .expect("tamper hash");

    let err = match Storage::open(db.to_string_lossy().to_string()) {
        Ok(_) => panic!("must reject bad audit chain"),
        Err(err) => err,
    };
    match err {
        StorageError::UnsafeState {
            code,
            message: _,
            details,
        } => {
            assert_eq!(code, "AUDIT_CHAIN_INVALID");
            assert_eq!(details["issueCount"], serde_json::json!(1));
            assert_eq!(
                details["issues"][0]["code"],
                serde_json::json!("AUDIT_CHAIN_TAMPERED_HASH")
            );
            assert_eq!(details["issues"][0]["event_id"], serde_json::json!(2));
        }
        other => panic!("unexpected error: {other:?}"),
    }
}
