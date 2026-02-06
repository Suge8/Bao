use bao_storage::{MemoryItemRecord, MemoryLinkRecord, MemoryVersionRecord, Storage};
use rusqlite::Connection;

const INIT_SQL: &str = include_str!("../migrations/0001_init.sql");

#[test]
fn memory_upsert_and_version_and_link() {
    let dir = tempfile::tempdir().expect("tempdir");
    let db = dir.path().join("test.sqlite");
    let conn = Connection::open(&db).expect("open");
    conn.execute_batch(INIT_SQL).expect("init schema");

    let storage = Storage::open(db.to_string_lossy().to_string()).expect("storage");
    let item = MemoryItemRecord {
        memory_id: "m1".to_string(),
        namespace: "n".to_string(),
        kind: "k".to_string(),
        title: "t".to_string(),
        content: Some("c".to_string()),
        json: None,
        score: 1.0,
        status: "active".to_string(),
        source_hash: None,
        created_at: 1,
        updated_at: 1,
        last_injected_at: None,
        inject_count: 0,
    };
    storage.upsert_memory_item(&item).expect("upsert");

    let version = MemoryVersionRecord {
        version_id: "v1".to_string(),
        memory_id: "m1".to_string(),
        prev_version_id: None,
        op: "UPSERT".to_string(),
        diff_json: "{}".to_string(),
        actor: "test".to_string(),
        created_at: 1,
    };
    storage.insert_memory_version(&version).expect("version");

    let link = MemoryLinkRecord {
        memory_id: "m1".to_string(),
        kind: "message".to_string(),
        message_id: Some("msg".to_string()),
        event_id: None,
        artifact_sha256: None,
        weight: 1.0,
        note: None,
        created_at: 1,
    };
    storage.insert_memory_link(&link).expect("link");
}

#[test]
fn audit_event_inserts_hash_chain() {
    let dir = tempfile::tempdir().expect("tempdir");
    let db = dir.path().join("test.sqlite");
    let conn = Connection::open(&db).expect("open");
    conn.execute_batch(INIT_SQL).expect("init schema");

    let storage = Storage::open(db.to_string_lossy().to_string()).expect("storage");
    storage
        .insert_audit_event(1, "act", "sub", "1", &serde_json::json!({"a": 1}))
        .expect("audit1");
    storage
        .insert_audit_event(2, "act", "sub", "2", &serde_json::json!({"a": 2}))
        .expect("audit2");
}
