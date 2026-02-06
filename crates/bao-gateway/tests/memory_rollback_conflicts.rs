use bao_gateway::GatewayServer;
use rusqlite::{params, Connection};

fn query_memory_ids(sqlite_path: &str) -> Vec<String> {
    let conn = Connection::open(sqlite_path).expect("open sqlite");
    let mut stmt = conn
        .prepare("SELECT memory_id FROM memory_items ORDER BY memory_id ASC")
        .expect("prepare query ids");
    let rows = stmt
        .query_map([], |r| r.get::<_, String>(0))
        .expect("query ids")
        .collect::<Result<Vec<_>, _>>()
        .expect("collect ids");
    rows
}

fn query_memory_content(sqlite_path: &str, memory_id: &str) -> Option<String> {
    let conn = Connection::open(sqlite_path).expect("open sqlite");
    conn.query_row(
        "SELECT content FROM memory_items WHERE memory_id=?1",
        params![memory_id],
        |r| r.get(0),
    )
    .ok()
}

fn first_version_id_by_op(versions: &[serde_json::Value], op: &str) -> String {
    versions
        .iter()
        .find(|v| {
            v.get("op")
                .and_then(serde_json::Value::as_str)
                .map(|x| x == op)
                .unwrap_or(false)
        })
        .and_then(|v| {
            v.get("version_id")
                .or_else(|| v.get("versionId"))
                .and_then(serde_json::Value::as_str)
        })
        .expect("version id by op")
        .to_string()
}

#[tokio::test]
async fn rollback_supersede_should_restore_old_memory_and_remove_new_memory() {
    let dir = tempfile::tempdir().expect("tempdir");
    let sqlite_path = dir.path().join("test.sqlite");
    let sqlite_path_str = sqlite_path.to_string_lossy().to_string();

    let (_gateway, handle) = GatewayServer::open(sqlite_path_str.clone()).expect("open gateway");

    handle
        .apply_mutation_plan(bao_api::MemoryMutationPlanV1 {
            planId: "p_upsert_old".to_string(),
            mutations: vec![bao_api::MemoryMutationV1 {
                op: bao_api::MemoryMutationOpV1::UPSERT,
                idempotencyKey: "k_upsert_old".to_string(),
                reason: Some("seed old".to_string()),
                memory: Some(bao_api::MemoryItemV1 {
                    id: Some("m_old".to_string()),
                    namespace: "test.ns".to_string(),
                    kind: "fact".to_string(),
                    title: "old".to_string(),
                    content: Some("old-content".to_string()),
                    json: None,
                    score: Some(0.5),
                    status: Some("active".to_string()),
                    sourceHash: Some("s_old".to_string()),
                }),
                supersede: None,
                delete: None,
                link: None,
            }],
            dangerous: None,
        })
        .await
        .expect("apply old upsert");

    handle
        .apply_mutation_plan(bao_api::MemoryMutationPlanV1 {
            planId: "p_supersede".to_string(),
            mutations: vec![bao_api::MemoryMutationV1 {
                op: bao_api::MemoryMutationOpV1::SUPERSEDE,
                idempotencyKey: "k_supersede".to_string(),
                reason: Some("replace old".to_string()),
                memory: Some(bao_api::MemoryItemV1 {
                    id: Some("m_new".to_string()),
                    namespace: "test.ns".to_string(),
                    kind: "fact".to_string(),
                    title: "new".to_string(),
                    content: Some("new-content".to_string()),
                    json: None,
                    score: Some(0.7),
                    status: Some("active".to_string()),
                    sourceHash: Some("s_new".to_string()),
                }),
                supersede: Some(bao_api::MemorySupersedeV1 {
                    oldId: "m_old".to_string(),
                    newId: "m_new".to_string(),
                }),
                delete: None,
                link: None,
            }],
            dangerous: None,
        })
        .await
        .expect("apply supersede");

    let versions_evt = handle
        .list_memory_versions("m_new".to_string())
        .await
        .expect("list versions m_new");
    let versions = versions_evt
        .payload
        .get("versions")
        .and_then(serde_json::Value::as_array)
        .cloned()
        .unwrap_or_default();
    let supersede_version_id = first_version_id_by_op(&versions, "SUPERSEDE");

    handle
        .rollback_version("m_new".to_string(), supersede_version_id)
        .await
        .expect("rollback supersede");

    let ids = query_memory_ids(&sqlite_path_str);
    assert!(ids.contains(&"m_old".to_string()));
    assert!(!ids.contains(&"m_new".to_string()));
    assert_eq!(
        query_memory_content(&sqlite_path_str, "m_old"),
        Some("old-content".to_string())
    );
}

#[tokio::test]
async fn rollback_delete_should_restore_deleted_memory_snapshot() {
    let dir = tempfile::tempdir().expect("tempdir");
    let sqlite_path = dir.path().join("test.sqlite");
    let sqlite_path_str = sqlite_path.to_string_lossy().to_string();

    let (_gateway, handle) = GatewayServer::open(sqlite_path_str.clone()).expect("open gateway");

    handle
        .apply_mutation_plan(bao_api::MemoryMutationPlanV1 {
            planId: "p_upsert_delete".to_string(),
            mutations: vec![bao_api::MemoryMutationV1 {
                op: bao_api::MemoryMutationOpV1::UPSERT,
                idempotencyKey: "k_upsert_delete".to_string(),
                reason: Some("seed delete".to_string()),
                memory: Some(bao_api::MemoryItemV1 {
                    id: Some("m_del".to_string()),
                    namespace: "test.ns".to_string(),
                    kind: "fact".to_string(),
                    title: "to-delete".to_string(),
                    content: Some("delete-me".to_string()),
                    json: None,
                    score: Some(0.5),
                    status: Some("active".to_string()),
                    sourceHash: Some("s_del".to_string()),
                }),
                supersede: None,
                delete: None,
                link: None,
            }],
            dangerous: None,
        })
        .await
        .expect("apply upsert for delete");

    handle
        .apply_mutation_plan(bao_api::MemoryMutationPlanV1 {
            planId: "p_delete".to_string(),
            mutations: vec![bao_api::MemoryMutationV1 {
                op: bao_api::MemoryMutationOpV1::DELETE,
                idempotencyKey: "k_delete".to_string(),
                reason: Some("delete".to_string()),
                memory: None,
                supersede: None,
                delete: Some(bao_api::MemoryDeleteV1 {
                    id: "m_del".to_string(),
                }),
                link: None,
            }],
            dangerous: None,
        })
        .await
        .expect("apply delete");

    assert_eq!(query_memory_content(&sqlite_path_str, "m_del"), None);

    let versions_evt = handle
        .list_memory_versions("m_del".to_string())
        .await
        .expect("list versions m_del");
    let versions = versions_evt
        .payload
        .get("versions")
        .and_then(serde_json::Value::as_array)
        .cloned()
        .unwrap_or_default();
    let delete_version_id = first_version_id_by_op(&versions, "DELETE");

    handle
        .rollback_version("m_del".to_string(), delete_version_id)
        .await
        .expect("rollback delete");

    assert_eq!(
        query_memory_content(&sqlite_path_str, "m_del"),
        Some("delete-me".to_string())
    );
}
