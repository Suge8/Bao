use bao_gateway::GatewayServer;

// TDD: These tests assert the desktop IPC surface we need to expose via GatewayHandle.

#[tokio::test]
async fn tasks_ipc_methods_exist_and_return_event() {
    let dir = tempfile::tempdir().expect("tempdir");
    let sqlite_path = dir.path().join("bao.sqlite");
    let (gateway, handle) = GatewayServer::open(sqlite_path.to_string_lossy().to_string())
        .expect("open gateway");
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

    let enable_evt: bao_api::BaoEventV1 = handle.enable_task("t1".to_string()).await.expect("enable");
    assert_eq!(enable_evt.r#type, "tasks.enable");

    let disable_evt: bao_api::BaoEventV1 = handle.disable_task("t1".to_string()).await.expect("disable");
    assert_eq!(disable_evt.r#type, "tasks.disable");

    let run_evt: bao_api::BaoEventV1 = handle.run_task_now("t1".to_string()).await.expect("run now");
    assert_eq!(run_evt.r#type, "tasks.runNow");
}

#[tokio::test]
async fn memory_ipc_methods_exist_and_return_event() {
    let dir = tempfile::tempdir().expect("tempdir");
    let sqlite_path = dir.path().join("bao.sqlite");
    let (gateway, handle) = GatewayServer::open(sqlite_path.to_string_lossy().to_string())
        .expect("open gateway");
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
            mutations: vec![],
            dangerous: None,
        })
        .await
        .expect("apply plan");
    assert_eq!(plan_evt.r#type, "memory.applyMutationPlan");

    let rollback_evt: bao_api::BaoEventV1 = handle
        .rollback_version("m1".to_string(), "v1".to_string())
        .await
        .expect("rollback");
    assert_eq!(rollback_evt.r#type, "memory.rollbackVersion");
}
