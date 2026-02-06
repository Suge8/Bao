use bao_gateway::GatewayServer;
use rusqlite::{params, Connection};

#[tokio::test]
async fn run_task_now_emits_event() {
    let dir = tempfile::tempdir().expect("tempdir");
    let sqlite_path = dir.path().join("test.sqlite");

    let (_gateway, handle) =
        GatewayServer::open(sqlite_path.to_string_lossy().to_string()).expect("open gateway");

    handle
        .create_task(bao_api::TaskSpecV1 {
            id: "t1".to_string(),
            title: "task".to_string(),
            enabled: true,
            schedule: bao_api::TaskScheduleV1 {
                kind: bao_api::TaskScheduleKindV1::Once,
                runAtTs: Some(1),
                intervalMs: None,
                cron: None,
                timezone: None,
            },
            action: bao_api::TaskActionV1 {
                kind: bao_api::TaskActionKindV1::ToolCall,
                toolCall: bao_api::TaskToolCallV1 {
                    dimsumId: "d1".to_string(),
                    toolName: "t1".to_string(),
                    args: serde_json::json!({"k": "v"}),
                },
            },
            policy: None,
        })
        .await
        .expect("create task");

    let evt = handle
        .run_task_now("t1".to_string())
        .await
        .expect("run now");
    assert_eq!(evt.r#type, "tasks.runNow");
}

#[tokio::test]
async fn apply_mutation_plan_emits_event() {
    let dir = tempfile::tempdir().expect("tempdir");
    let sqlite_path = dir.path().join("test.sqlite");

    let (_gateway, handle) =
        GatewayServer::open(sqlite_path.to_string_lossy().to_string()).expect("open gateway");

    let evt = handle
        .apply_mutation_plan(bao_api::MemoryMutationPlanV1 {
            planId: "p1".to_string(),
            mutations: vec![],
            dangerous: None,
        })
        .await
        .expect("apply plan");
    assert_eq!(evt.r#type, "memory.applyMutationPlan");
}

#[tokio::test]
async fn list_memory_versions_emits_event() {
    let dir = tempfile::tempdir().expect("tempdir");
    let sqlite_path = dir.path().join("test.sqlite");

    let (_gateway, handle) =
        GatewayServer::open(sqlite_path.to_string_lossy().to_string()).expect("open gateway");

    let evt = handle
        .list_memory_versions("m1".to_string())
        .await
        .expect("list versions");
    assert_eq!(evt.r#type, "memory.listVersions");
}

#[tokio::test]
async fn run_task_now_unauthorized_should_be_rejected_with_event_and_audit() {
    let dir = tempfile::tempdir().expect("tempdir");
    let sqlite_path = dir.path().join("unauthorized.sqlite");

    let (_gateway, handle) =
        GatewayServer::open(sqlite_path.to_string_lossy().to_string()).expect("open gateway");

    let conn = Connection::open(&sqlite_path).expect("open sqlite");
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

    handle
        .update_setting(
            "permissions.capabilities".to_string(),
            serde_json::json!({"cmd.exec": false}),
        )
        .await
        .expect("set capabilities");

    handle
        .create_task(bao_api::TaskSpecV1 {
            id: "t1".to_string(),
            title: "task".to_string(),
            enabled: true,
            schedule: bao_api::TaskScheduleV1 {
                kind: bao_api::TaskScheduleKindV1::Once,
                runAtTs: Some(1),
                intervalMs: None,
                cron: None,
                timezone: None,
            },
            action: bao_api::TaskActionV1 {
                kind: bao_api::TaskActionKindV1::ToolCall,
                toolCall: bao_api::TaskToolCallV1 {
                    dimsumId: "d1".to_string(),
                    toolName: "t1".to_string(),
                    args: serde_json::json!({"k": "v"}),
                },
            },
            policy: None,
        })
        .await
        .expect("create task");

    let evt = handle
        .run_task_now("t1".to_string())
        .await
        .expect("run now");
    assert_eq!(evt.r#type, "tasks.runNow");

    let rejected_count: i64 = conn
        .query_row(
            "SELECT COUNT(1) FROM events WHERE type='task.run.rejected'",
            [],
            |r| r.get(0),
        )
        .expect("rejected event count");
    assert_eq!(rejected_count, 1);

    let audit_row: (String, String) = conn
        .query_row(
            "SELECT action, payload_json FROM audit_events WHERE action='task.run.rejected' ORDER BY id DESC LIMIT 1",
            [],
            |r| Ok((r.get(0)?, r.get(1)?)),
        )
        .expect("rejected audit row");
    assert_eq!(audit_row.0, "task.run.rejected");
    let payload: serde_json::Value = serde_json::from_str(&audit_row.1).expect("parse payload");
    assert_eq!(payload["code"], "PERMISSION_CAPABILITY_DENIED");
}
