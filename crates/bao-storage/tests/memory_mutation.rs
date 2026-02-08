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

#[test]
fn audit_chain_verifier_passes_for_valid_chain() {
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

    let report = storage.verify_audit_chain().expect("verify");
    assert!(report.ok);
    assert_eq!(report.checked_events, 2);
    assert_eq!(report.issue_count, 0);
    assert!(report.issues.is_empty());
}

#[test]
fn audit_chain_verifier_detects_tampered_hash() {
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

    let conn = Connection::open(&db).expect("open for tamper");
    conn.execute("UPDATE audit_events SET hash='deadbeef' WHERE id=2", [])
        .expect("tamper hash");

    let report = storage.verify_audit_chain().expect("verify");
    assert!(!report.ok);
    assert_eq!(report.issue_count, 1);
    assert_eq!(report.issues[0].code, "AUDIT_CHAIN_TAMPERED_HASH");
    assert_eq!(report.issues[0].event_id, 2);
}

#[test]
fn audit_chain_verifier_detects_missing_link() {
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

    let conn = Connection::open(&db).expect("open for tamper");
    conn.execute("UPDATE audit_events SET prev_hash=NULL WHERE id=2", [])
        .expect("remove prev hash");

    let report = storage.verify_audit_chain().expect("verify");
    assert!(!report.ok);
    assert!(report.issue_count >= 1);
    assert!(report
        .issues
        .iter()
        .any(|issue| issue.code == "AUDIT_CHAIN_MISSING_LINK" && issue.event_id == 2));
}

#[test]
fn audit_chain_verifier_detects_out_of_order_write() {
    let dir = tempfile::tempdir().expect("tempdir");
    let db = dir.path().join("test.sqlite");
    let conn = Connection::open(&db).expect("open");
    conn.execute_batch(INIT_SQL).expect("init schema");

    let storage = Storage::open(db.to_string_lossy().to_string()).expect("storage");
    storage
        .insert_audit_event(2, "act", "sub", "1", &serde_json::json!({"a": 1}))
        .expect("audit1");
    storage
        .insert_audit_event(1, "act", "sub", "2", &serde_json::json!({"a": 2}))
        .expect("audit2");

    let report = storage.verify_audit_chain().expect("verify");
    assert!(!report.ok);
    assert_eq!(report.issue_count, 1);
    assert_eq!(report.issues[0].code, "AUDIT_CHAIN_OUT_OF_ORDER_WRITE");
    assert_eq!(report.issues[0].event_id, 2);
}

#[test]
fn audit_chain_verifier_has_machine_readable_fields() {
    let dir = tempfile::tempdir().expect("tempdir");
    let db = dir.path().join("test.sqlite");
    let conn = Connection::open(&db).expect("open");
    conn.execute_batch(INIT_SQL).expect("init schema");

    let storage = Storage::open(db.to_string_lossy().to_string()).expect("storage");
    storage
        .insert_audit_event(2, "act", "sub", "1", &serde_json::json!({"a": 1}))
        .expect("audit1");
    storage
        .insert_audit_event(1, "act", "sub", "2", &serde_json::json!({"a": 2}))
        .expect("audit2");

    let report = storage.verify_audit_chain().expect("verify");
    let json = serde_json::to_value(report).expect("to json");

    assert_eq!(json["ok"], serde_json::json!(false));
    assert_eq!(json["checked_events"], serde_json::json!(2));
    assert_eq!(json["issue_count"], serde_json::json!(1));
    assert_eq!(
        json["issues"][0]["code"],
        serde_json::json!("AUDIT_CHAIN_OUT_OF_ORDER_WRITE")
    );
    assert_eq!(json["issues"][0]["event_id"], serde_json::json!(2));
}

#[test]
fn list_audit_events_since_should_support_cursor_and_limit() {
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

    let first_page = storage
        .list_audit_events_since(None, 1)
        .expect("list first page");
    assert_eq!(first_page.len(), 1);

    let second_page = storage
        .list_audit_events_since(Some(first_page[0].id), 10)
        .expect("list second page");
    assert_eq!(second_page.len(), 1);
    assert_eq!(second_page[0].subject_id, "2");
    assert_eq!(second_page[0].payload["a"], serde_json::json!(2));
}
