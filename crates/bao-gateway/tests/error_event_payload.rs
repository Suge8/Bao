use bao_gateway::GatewayServer;
use serde_json::{json, Value};

fn assert_has_string_field(payload: &Value, key: &str) {
    let value = payload.get(key).and_then(Value::as_str).unwrap_or_default();
    assert!(
        !value.trim().is_empty(),
        "payload field {key} should be non-empty string: {payload}"
    );
}

fn assert_common_error_payload(payload: &Value) {
    assert_has_string_field(payload, "source");
    assert_has_string_field(payload, "stage");
    assert_has_string_field(payload, "sessionId");
    assert_has_string_field(payload, "error");
    assert_has_string_field(payload, "code");
}

#[tokio::test]
async fn emit_event_should_keep_corrector_error_payload_complete() {
    let dir = tempfile::tempdir().expect("tempdir");
    let sqlite_path = dir.path().join("test.sqlite");

    let (_gateway, handle) =
        GatewayServer::open(sqlite_path.to_string_lossy().to_string()).expect("open gateway");

    let payload = json!({
      "source": "runEngineTurn",
      "stage": "corrector.validate_tool_result",
      "sessionId": "s1",
      "error": "validator unavailable",
      "code": "ERR_CORRECTOR_VALIDATE_TOOL_RESULT",
      "toolName": "shell.exec",
      "attempt": 1,
    });

    let evt = handle
        .emit_event(
            "corrector.validate_tool_result.error".to_string(),
            Some("s1".to_string()),
            payload,
        )
        .await
        .expect("emit event");

    assert_eq!(evt.r#type, "corrector.validate_tool_result.error");
    assert_common_error_payload(&evt.payload);
    assert_eq!(evt.payload.get("toolName"), Some(&json!("shell.exec")));
    assert_eq!(evt.payload.get("attempt"), Some(&json!(1)));
    assert_eq!(
        evt.payload.get("code"),
        Some(&json!("ERR_CORRECTOR_VALIDATE_TOOL_RESULT"))
    );

    let replay = handle
        .events_since(Some(evt.eventId - 1), 10)
        .await
        .expect("events since");
    let replay_evt = replay
        .into_iter()
        .find(|item| item.eventId == evt.eventId)
        .expect("event should be replayable");
    assert_common_error_payload(&replay_evt.payload);
    assert_eq!(replay_evt.payload.get("toolName"), Some(&json!("shell.exec")));
    assert_eq!(replay_evt.payload.get("attempt"), Some(&json!(1)));
    assert_eq!(
        replay_evt.payload.get("code"),
        Some(&json!("ERR_CORRECTOR_VALIDATE_TOOL_RESULT"))
    );
}

#[tokio::test]
async fn emit_event_should_keep_memory_error_payload_complete() {
    let dir = tempfile::tempdir().expect("tempdir");
    let sqlite_path = dir.path().join("test.sqlite");

    let (_gateway, handle) =
        GatewayServer::open(sqlite_path.to_string_lossy().to_string()).expect("open gateway");

    let payload = json!({
      "source": "runEngineTurn",
      "stage": "memory.extract.apply_plan",
      "sessionId": "s1",
      "error": "apply mutation plan failed",
      "code": "ERR_MEMORY_EXTRACT_APPLY_PLAN",
      "planId": "plan_1",
      "mutationCount": 1,
    });

    let evt = handle
        .emit_event(
            "memory.extract.error".to_string(),
            Some("s1".to_string()),
            payload,
        )
        .await
        .expect("emit event");

    assert_eq!(evt.r#type, "memory.extract.error");
    assert_common_error_payload(&evt.payload);
    assert_eq!(evt.payload.get("planId"), Some(&json!("plan_1")));
    assert_eq!(evt.payload.get("mutationCount"), Some(&json!(1)));
    assert_eq!(
        evt.payload.get("code"),
        Some(&json!("ERR_MEMORY_EXTRACT_APPLY_PLAN"))
    );

    let replay = handle
        .events_since(Some(evt.eventId - 1), 10)
        .await
        .expect("events since");
    let replay_evt = replay
        .into_iter()
        .find(|item| item.eventId == evt.eventId)
        .expect("event should be replayable");
    assert_common_error_payload(&replay_evt.payload);
    assert_eq!(replay_evt.payload.get("planId"), Some(&json!("plan_1")));
    assert_eq!(replay_evt.payload.get("mutationCount"), Some(&json!(1)));
    assert_eq!(
        replay_evt.payload.get("code"),
        Some(&json!("ERR_MEMORY_EXTRACT_APPLY_PLAN"))
    );
}

#[tokio::test]
async fn emit_event_should_keep_provider_error_payload_complete() {
    let dir = tempfile::tempdir().expect("tempdir");
    let sqlite_path = dir.path().join("test.sqlite");

    let (_gateway, handle) =
        GatewayServer::open(sqlite_path.to_string_lossy().to_string()).expect("open gateway");

    let payload = json!({
      "source": "runEngineTurn",
      "stage": "provider.call",
      "sessionId": "s1",
      "error": "provider run timeout",
      "code": "ERR_PROVIDER_CALL",
      "provider": "bao.bundled.provider.openai",
      "model": "gpt-4.1-mini",
      "attempt": 1,
    });

    let evt = handle
        .emit_event(
            "provider.call.error".to_string(),
            Some("s1".to_string()),
            payload,
        )
        .await
        .expect("emit event");

    assert_eq!(evt.r#type, "provider.call.error");
    assert_common_error_payload(&evt.payload);
    assert_eq!(
        evt.payload.get("provider"),
        Some(&json!("bao.bundled.provider.openai"))
    );
    assert_eq!(evt.payload.get("model"), Some(&json!("gpt-4.1-mini")));
    assert_eq!(evt.payload.get("attempt"), Some(&json!(1)));
    assert_eq!(evt.payload.get("code"), Some(&json!("ERR_PROVIDER_CALL")));

    let replay = handle
        .events_since(Some(evt.eventId - 1), 10)
        .await
        .expect("events since");
    let replay_evt = replay
        .into_iter()
        .find(|item| item.eventId == evt.eventId)
        .expect("event should be replayable");
    assert_common_error_payload(&replay_evt.payload);
    assert_eq!(
        replay_evt.payload.get("provider"),
        Some(&json!("bao.bundled.provider.openai"))
    );
    assert_eq!(replay_evt.payload.get("model"), Some(&json!("gpt-4.1-mini")));
    assert_eq!(replay_evt.payload.get("attempt"), Some(&json!(1)));
    assert_eq!(replay_evt.payload.get("code"), Some(&json!("ERR_PROVIDER_CALL")));
}

#[tokio::test]
async fn emit_event_should_keep_corrector_retry_error_payload_complete() {
    let dir = tempfile::tempdir().expect("tempdir");
    let sqlite_path = dir.path().join("test.sqlite");

    let (_gateway, handle) =
        GatewayServer::open(sqlite_path.to_string_lossy().to_string()).expect("open gateway");

    let payload = json!({
      "source": "runEngineTurn",
      "stage": "corrector.decide_retry",
      "sessionId": "s1",
      "error": "retry checker unavailable",
      "code": "ERR_CORRECTOR_DECIDE_RETRY",
      "toolName": "shell.exec",
      "attempt": 1,
    });

    let evt = handle
        .emit_event(
            "corrector.decide_retry.error".to_string(),
            Some("s1".to_string()),
            payload,
        )
        .await
        .expect("emit event");

    assert_eq!(evt.r#type, "corrector.decide_retry.error");
    assert_common_error_payload(&evt.payload);
    assert_eq!(evt.payload.get("toolName"), Some(&json!("shell.exec")));
    assert_eq!(evt.payload.get("attempt"), Some(&json!(1)));
    assert_eq!(
        evt.payload.get("code"),
        Some(&json!("ERR_CORRECTOR_DECIDE_RETRY"))
    );

    let replay = handle
        .events_since(Some(evt.eventId - 1), 10)
        .await
        .expect("events since");
    let replay_evt = replay
        .into_iter()
        .find(|item| item.eventId == evt.eventId)
        .expect("event should be replayable");
    assert_common_error_payload(&replay_evt.payload);
    assert_eq!(replay_evt.payload.get("toolName"), Some(&json!("shell.exec")));
    assert_eq!(replay_evt.payload.get("attempt"), Some(&json!(1)));
    assert_eq!(
        replay_evt.payload.get("code"),
        Some(&json!("ERR_CORRECTOR_DECIDE_RETRY"))
    );
}

#[tokio::test]
async fn emit_event_should_keep_memory_inject_error_payload_complete() {
    let dir = tempfile::tempdir().expect("tempdir");
    let sqlite_path = dir.path().join("test.sqlite");

    let (_gateway, handle) =
        GatewayServer::open(sqlite_path.to_string_lossy().to_string()).expect("open gateway");

    let payload = json!({
      "source": "runEngineTurn",
      "stage": "memory.inject.pipeline",
      "sessionId": "s1",
      "error": "memory inject failed",
      "code": "ERR_MEMORY_INJECT_PIPELINE",
      "memoryQuery": "偏好",
    });

    let evt = handle
        .emit_event(
            "memory.inject.error".to_string(),
            Some("s1".to_string()),
            payload,
        )
        .await
        .expect("emit event");

    assert_eq!(evt.r#type, "memory.inject.error");
    assert_common_error_payload(&evt.payload);
    assert_eq!(evt.payload.get("memoryQuery"), Some(&json!("偏好")));
    assert_eq!(
        evt.payload.get("code"),
        Some(&json!("ERR_MEMORY_INJECT_PIPELINE"))
    );

    let replay = handle
        .events_since(Some(evt.eventId - 1), 10)
        .await
        .expect("events since");
    let replay_evt = replay
        .into_iter()
        .find(|item| item.eventId == evt.eventId)
        .expect("event should be replayable");
    assert_common_error_payload(&replay_evt.payload);
    assert_eq!(replay_evt.payload.get("memoryQuery"), Some(&json!("偏好")));
    assert_eq!(
        replay_evt.payload.get("code"),
        Some(&json!("ERR_MEMORY_INJECT_PIPELINE"))
    );
}
