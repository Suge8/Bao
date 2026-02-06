use bao_gateway::GatewayServer;
use rusqlite::{params, Connection};

// TDD: These tests assert the desktop IPC surface we need to expose via GatewayHandle.

#[tokio::test]
async fn tasks_ipc_methods_exist_and_return_event() {
    let dir = tempfile::tempdir().expect("tempdir");
    let sqlite_path = dir.path().join("bao.sqlite");
    let (gateway, handle) =
        GatewayServer::open(sqlite_path.to_string_lossy().to_string()).expect("open gateway");
    drop(gateway);

    // Minimal create -> list flow.
    let evt = handle
        .create_task(bao_api::TaskSpecV1 {
            id: "t1".to_string(),
            title: "Test".to_string(),
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
                    toolName: "noop".to_string(),
                    args: serde_json::json!({}),
                },
            },
            policy: None,
        })
        .await
        .expect("create task");
    assert_eq!(evt.r#type, "tasks.create");

    let list_evt = handle.list_tasks().await.expect("list tasks");
    assert_eq!(list_evt.r#type, "tasks.list");

    let update_evt: bao_api::BaoEventV1 = handle
        .update_task(bao_api::TaskSpecV1 {
            id: "t1".to_string(),
            title: "Test Updated".to_string(),
            enabled: true,
            schedule: bao_api::TaskScheduleV1 {
                kind: bao_api::TaskScheduleKindV1::Once,
                runAtTs: Some(2),
                intervalMs: None,
                cron: None,
                timezone: None,
            },
            action: bao_api::TaskActionV1 {
                kind: bao_api::TaskActionKindV1::ToolCall,
                toolCall: bao_api::TaskToolCallV1 {
                    dimsumId: "d1".to_string(),
                    toolName: "noop".to_string(),
                    args: serde_json::json!({}),
                },
            },
            policy: None,
        })
        .await
        .expect("update task");
    assert_eq!(update_evt.r#type, "tasks.update");

    let enable_evt: bao_api::BaoEventV1 =
        handle.enable_task("t1".to_string()).await.expect("enable");
    assert_eq!(enable_evt.r#type, "tasks.enable");

    let disable_evt: bao_api::BaoEventV1 = handle
        .disable_task("t1".to_string())
        .await
        .expect("disable");
    assert_eq!(disable_evt.r#type, "tasks.disable");

    let run_evt: bao_api::BaoEventV1 = handle
        .run_task_now("t1".to_string())
        .await
        .expect("run now");
    assert_eq!(run_evt.r#type, "tasks.runNow");
}

#[tokio::test]
async fn task_next_run_should_be_computed_for_interval_and_cron() {
    let dir = tempfile::tempdir().expect("tempdir");
    let sqlite_path = dir.path().join("bao.sqlite");
    let sqlite_path_str = sqlite_path.to_string_lossy().to_string();
    let (_gateway, handle) = GatewayServer::open(sqlite_path_str.clone()).expect("open gateway");

    handle
        .create_task(bao_api::TaskSpecV1 {
            id: "interval_task".to_string(),
            title: "Interval".to_string(),
            enabled: true,
            schedule: bao_api::TaskScheduleV1 {
                kind: bao_api::TaskScheduleKindV1::Interval,
                runAtTs: None,
                intervalMs: Some(60_000),
                cron: None,
                timezone: None,
            },
            action: bao_api::TaskActionV1 {
                kind: bao_api::TaskActionKindV1::ToolCall,
                toolCall: bao_api::TaskToolCallV1 {
                    dimsumId: "d1".to_string(),
                    toolName: "noop".to_string(),
                    args: serde_json::json!({}),
                },
            },
            policy: None,
        })
        .await
        .expect("create interval task");

    handle
        .create_task(bao_api::TaskSpecV1 {
            id: "cron_task".to_string(),
            title: "Cron".to_string(),
            enabled: true,
            schedule: bao_api::TaskScheduleV1 {
                kind: bao_api::TaskScheduleKindV1::Cron,
                runAtTs: None,
                intervalMs: None,
                cron: Some("0 * * * * *".to_string()),
                timezone: None,
            },
            action: bao_api::TaskActionV1 {
                kind: bao_api::TaskActionKindV1::ToolCall,
                toolCall: bao_api::TaskToolCallV1 {
                    dimsumId: "d1".to_string(),
                    toolName: "noop".to_string(),
                    args: serde_json::json!({}),
                },
            },
            policy: None,
        })
        .await
        .expect("create cron task");

    let conn = Connection::open(sqlite_path_str).expect("open sqlite");

    let interval_next_run_at: Option<i64> = conn
        .query_row(
            "SELECT next_run_at FROM tasks WHERE task_id=?1",
            params!["interval_task"],
            |r| r.get(0),
        )
        .expect("query interval next_run_at");

    let cron_next_run_at: Option<i64> = conn
        .query_row(
            "SELECT next_run_at FROM tasks WHERE task_id=?1",
            params!["cron_task"],
            |r| r.get(0),
        )
        .expect("query cron next_run_at");

    assert!(interval_next_run_at.is_some());
    assert!(cron_next_run_at.is_some());

    handle
        .disable_task("interval_task".to_string())
        .await
        .expect("disable interval task");
    handle
        .enable_task("interval_task".to_string())
        .await
        .expect("enable interval task");

    let interval_next_run_after_enable: Option<i64> = conn
        .query_row(
            "SELECT next_run_at FROM tasks WHERE task_id=?1",
            params!["interval_task"],
            |r| r.get(0),
        )
        .expect("query interval next_run_at after enable");

    assert!(interval_next_run_after_enable.is_some());
}

#[tokio::test]
async fn memory_ipc_methods_exist_and_return_event() {
    let dir = tempfile::tempdir().expect("tempdir");
    let sqlite_path = dir.path().join("bao.sqlite");
    let (gateway, handle) =
        GatewayServer::open(sqlite_path.to_string_lossy().to_string()).expect("open gateway");
    drop(gateway);

    // Minimal search flow: empty query should still succeed.
    // Minimal search flow: empty query should still succeed.
    let evt: bao_api::BaoEventV1 = handle
        .search_index("".to_string(), 10)
        .await
        .expect("search index");
    assert_eq!(evt.r#type, "memory.searchIndex");

    let item_evt: bao_api::BaoEventV1 = handle
        .get_items(vec!["m1".to_string()])
        .await
        .expect("get items");
    assert_eq!(item_evt.r#type, "memory.getItems");

    let timeline_evt: bao_api::BaoEventV1 = handle.get_timeline(None).await.expect("timeline");
    assert_eq!(timeline_evt.r#type, "memory.getTimeline");

    let plan_evt: bao_api::BaoEventV1 = handle
        .apply_mutation_plan(bao_api::MemoryMutationPlanV1 {
            planId: "p1".to_string(),
            mutations: vec![bao_api::MemoryMutationV1 {
                op: bao_api::MemoryMutationOpV1::UPSERT,
                idempotencyKey: "k1".to_string(),
                reason: Some("test".to_string()),
                memory: Some(bao_api::MemoryItemV1 {
                    id: Some("m1".to_string()),
                    namespace: "test.ns".to_string(),
                    kind: "note".to_string(),
                    title: "title".to_string(),
                    content: Some("content".to_string()),
                    json: None,
                    score: Some(0.6),
                    status: Some("active".to_string()),
                    sourceHash: Some("s1".to_string()),
                }),
                supersede: None,
                delete: None,
                link: None,
            }],
            dangerous: None,
        })
        .await
        .expect("apply plan");
    assert_eq!(plan_evt.r#type, "memory.applyMutationPlan");

    let versions_evt: bao_api::BaoEventV1 = handle
        .list_memory_versions("m1".to_string())
        .await
        .expect("list versions");
    assert_eq!(versions_evt.r#type, "memory.listVersions");

    let versions = versions_evt
        .payload
        .get("versions")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();
    let version_id = versions
        .first()
        .and_then(|v| v.get("version_id").or_else(|| v.get("versionId")))
        .and_then(|v| v.as_str())
        .expect("version id")
        .to_string();

    let rollback_evt: bao_api::BaoEventV1 = handle
        .rollback_version("m1".to_string(), version_id)
        .await
        .expect("rollback");
    assert_eq!(rollback_evt.r#type, "memory.rollbackVersion");
}

#[tokio::test]
async fn create_task_should_reject_invalid_schedule_inputs() {
    let dir = tempfile::tempdir().expect("tempdir");
    let sqlite_path = dir.path().join("bao.sqlite");
    let (_gateway, handle) =
        GatewayServer::open(sqlite_path.to_string_lossy().to_string()).expect("open gateway");

    let interval_err = handle
        .create_task(bao_api::TaskSpecV1 {
            id: "bad_interval".to_string(),
            title: "Bad Interval".to_string(),
            enabled: true,
            schedule: bao_api::TaskScheduleV1 {
                kind: bao_api::TaskScheduleKindV1::Interval,
                runAtTs: None,
                intervalMs: Some(500),
                cron: None,
                timezone: None,
            },
            action: bao_api::TaskActionV1 {
                kind: bao_api::TaskActionKindV1::ToolCall,
                toolCall: bao_api::TaskToolCallV1 {
                    dimsumId: "d1".to_string(),
                    toolName: "noop".to_string(),
                    args: serde_json::json!({}),
                },
            },
            policy: None,
        })
        .await
        .expect_err("interval task should be rejected");
    let interval_msg = interval_err.to_string();
    assert!(
        interval_msg.contains("schedule.intervalMs")
            || interval_msg.contains("intervalMs")
            || interval_msg.contains("minimum")
    );

    let timezone_err = handle
        .create_task(bao_api::TaskSpecV1 {
            id: "bad_tz".to_string(),
            title: "Bad Timezone".to_string(),
            enabled: true,
            schedule: bao_api::TaskScheduleV1 {
                kind: bao_api::TaskScheduleKindV1::Cron,
                runAtTs: None,
                intervalMs: None,
                cron: Some("0 * * * * *".to_string()),
                timezone: Some("Mars/Nowhere".to_string()),
            },
            action: bao_api::TaskActionV1 {
                kind: bao_api::TaskActionKindV1::ToolCall,
                toolCall: bao_api::TaskToolCallV1 {
                    dimsumId: "d1".to_string(),
                    toolName: "noop".to_string(),
                    args: serde_json::json!({}),
                },
            },
            policy: None,
        })
        .await
        .expect_err("cron timezone should be rejected");
    assert!(timezone_err.to_string().contains("schedule.timezone"));
}

#[tokio::test]
async fn update_task_should_reject_invalid_cron_expression() {
    let dir = tempfile::tempdir().expect("tempdir");
    let sqlite_path = dir.path().join("bao.sqlite");
    let (_gateway, handle) =
        GatewayServer::open(sqlite_path.to_string_lossy().to_string()).expect("open gateway");

    handle
        .create_task(bao_api::TaskSpecV1 {
            id: "task_update_cron".to_string(),
            title: "Update Cron".to_string(),
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
                    toolName: "noop".to_string(),
                    args: serde_json::json!({}),
                },
            },
            policy: None,
        })
        .await
        .expect("create base task");

    let err = handle
        .update_task(bao_api::TaskSpecV1 {
            id: "task_update_cron".to_string(),
            title: "Update Cron".to_string(),
            enabled: true,
            schedule: bao_api::TaskScheduleV1 {
                kind: bao_api::TaskScheduleKindV1::Cron,
                runAtTs: None,
                intervalMs: None,
                cron: Some("* * *".to_string()),
                timezone: Some("UTC".to_string()),
            },
            action: bao_api::TaskActionV1 {
                kind: bao_api::TaskActionKindV1::ToolCall,
                toolCall: bao_api::TaskToolCallV1 {
                    dimsumId: "d1".to_string(),
                    toolName: "noop".to_string(),
                    args: serde_json::json!({}),
                },
            },
            policy: None,
        })
        .await
        .expect_err("invalid cron should be rejected");

    assert!(err.to_string().contains("schedule.cron"));
}
