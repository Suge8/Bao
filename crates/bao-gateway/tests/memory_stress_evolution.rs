use bao_api::{
    MemoryDeleteV1, MemoryItemV1, MemoryMutationOpV1, MemoryMutationPlanV1, MemoryMutationV1,
    MemorySupersedeV1,
};
use bao_gateway::GatewayServer;
use rusqlite::{params, Connection};

fn upsert_mutation(memory_id: String, content: String, key: String) -> MemoryMutationV1 {
    MemoryMutationV1 {
        op: MemoryMutationOpV1::UPSERT,
        idempotencyKey: key,
        reason: Some("stress-seed".to_string()),
        memory: Some(MemoryItemV1 {
            id: Some(memory_id.clone()),
            namespace: "stress.user".to_string(),
            kind: "fact".to_string(),
            title: format!("pref-{memory_id}"),
            content: Some(content),
            json: None,
            score: Some(0.75),
            status: Some("active".to_string()),
            sourceHash: Some(format!("hash-{memory_id}")),
        }),
        supersede: None,
        delete: None,
        link: None,
    }
}

#[tokio::test]
async fn memory_evolution_should_hold_under_large_mutation_batches() {
    let dir = tempfile::tempdir().expect("tempdir");
    let sqlite_path = dir.path().join("stress.sqlite");
    let sqlite_path_str = sqlite_path.to_string_lossy().to_string();
    let (_gateway, handle) = GatewayServer::open(sqlite_path_str.clone()).expect("open gateway");

    let total = 1_200usize;
    let batch = 200usize;
    for start in (0..total).step_by(batch) {
        let end = (start + batch).min(total);
        let mutations = (start..end)
            .map(|i| {
                upsert_mutation(
                    format!("m_stress_{i}"),
                    format!("user-pref-{i}"),
                    format!("idem_stress_{i}"),
                )
            })
            .collect::<Vec<_>>();

        handle
            .apply_mutation_plan(MemoryMutationPlanV1 {
                planId: format!("plan_stress_{start}_{end}"),
                mutations,
                dangerous: None,
            })
            .await
            .expect("apply stress batch");
    }

    let search_evt = handle
        .search_index("pref".to_string(), 200)
        .await
        .expect("search stress memory");
    assert_eq!(search_evt.r#type, "memory.searchIndex");
    let hits = search_evt
        .payload
        .get("hits")
        .and_then(serde_json::Value::as_array)
        .cloned()
        .unwrap_or_default();
    assert!(!hits.is_empty(), "stress search should return hits");

    let ids = hits
        .iter()
        .take(20)
        .filter_map(|v| {
            v.get("id")
                .or_else(|| v.get("memoryId"))
                .and_then(serde_json::Value::as_str)
                .map(str::to_string)
        })
        .collect::<Vec<_>>();
    let get_evt = handle.get_items(ids).await.expect("get stress items");
    assert_eq!(get_evt.r#type, "memory.getItems");
    assert!(
        get_evt
            .payload
            .get("items")
            .and_then(serde_json::Value::as_array)
            .map(|v| !v.is_empty())
            .unwrap_or(false),
        "get_items should return non-empty items"
    );

    let superseded_old = "m_stress_1100".to_string();
    let superseded_new = "m_stress_1100_new".to_string();
    handle
        .apply_mutation_plan(MemoryMutationPlanV1 {
            planId: "plan_stress_supersede".to_string(),
            mutations: vec![MemoryMutationV1 {
                op: MemoryMutationOpV1::SUPERSEDE,
                idempotencyKey: "idem_stress_supersede".to_string(),
                reason: Some("stress-supersede".to_string()),
                memory: Some(MemoryItemV1 {
                    id: Some(superseded_new.clone()),
                    namespace: "stress.user".to_string(),
                    kind: "fact".to_string(),
                    title: "pref-superseded".to_string(),
                    content: Some("user-pref-1100-new".to_string()),
                    json: None,
                    score: Some(0.91),
                    status: Some("active".to_string()),
                    sourceHash: Some("hash-superseded".to_string()),
                }),
                supersede: Some(MemorySupersedeV1 {
                    oldId: superseded_old.clone(),
                    newId: superseded_new.clone(),
                }),
                delete: None,
                link: None,
            }],
            dangerous: None,
        })
        .await
        .expect("apply supersede in stress test");

    let versions_evt = handle
        .list_memory_versions(superseded_new.clone())
        .await
        .expect("list superseded versions");
    let versions = versions_evt
        .payload
        .get("versions")
        .and_then(serde_json::Value::as_array)
        .cloned()
        .unwrap_or_default();
    let supersede_version_id = versions
        .iter()
        .find(|v| v.get("op").and_then(serde_json::Value::as_str) == Some("SUPERSEDE"))
        .and_then(|v| {
            v.get("version_id")
                .or_else(|| v.get("versionId"))
                .and_then(serde_json::Value::as_str)
        })
        .expect("supersede version id")
        .to_string();

    handle
        .rollback_version(superseded_new, supersede_version_id)
        .await
        .expect("rollback supersede in stress test");

    let conn = Connection::open(sqlite_path_str).expect("open sqlite");
    let restored_count: i64 = conn
        .query_row(
            "SELECT COUNT(1) FROM memory_items WHERE memory_id=?1",
            params![superseded_old],
            |r| r.get(0),
        )
        .expect("query restored memory");
    assert_eq!(restored_count, 1, "old memory should be restored after rollback");

    let delete_evt = handle
        .apply_mutation_plan(MemoryMutationPlanV1 {
            planId: "plan_stress_delete".to_string(),
            mutations: vec![MemoryMutationV1 {
                op: MemoryMutationOpV1::DELETE,
                idempotencyKey: "idem_stress_delete".to_string(),
                reason: Some("stress-delete".to_string()),
                memory: None,
                supersede: None,
                delete: Some(MemoryDeleteV1 {
                    id: "m_stress_1199".to_string(),
                }),
                link: None,
            }],
            dangerous: None,
        })
        .await
        .expect("apply delete in stress test");
    assert_eq!(delete_evt.r#type, "memory.applyMutationPlan");
}
