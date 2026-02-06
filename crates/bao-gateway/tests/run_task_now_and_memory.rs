use bao_gateway::GatewayServer;

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
