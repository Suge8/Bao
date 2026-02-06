use std::time::{SystemTime, UNIX_EPOCH};

use bao_api::{
    MemoryItemV1, MemoryMutationOpV1, MemoryMutationPlanV1, MemoryMutationV1, ToolCallIrV1,
};
use bao_engine::{
    CorrectorHook, DefaultCorrectorHook, DefaultMemoryHook, DefaultRouterHook, MemoryHook,
    RouterHook,
};
use serde_json::{json, Value};

use crate::jsonrpc::{run_server, RpcError};

pub fn run_router_server() -> Result<(), String> {
    let hook = DefaultRouterHook;
    run_server(|method, params| match method {
        "router.methods" => Ok(json!({
            "methods": [
                {
                    "method": "router.route",
                    "paramsSchemaRef": "bao.router.input/v1",
                    "resultSchemaRef": "bao.router.output/v1",
                    "notification": false
                }
            ]
        })),
        "router.route" => {
            let user_input = extract_user_input(params)?;
            let out = hook.route(&user_input);
            serde_json::to_value(out).map_err(|e| RpcError::internal(e.to_string()))
        }
        _ => Err(RpcError::method_not_found(method)),
    })
    .map_err(|e| e.to_string())
}

pub fn run_memory_server() -> Result<(), String> {
    let hook = DefaultMemoryHook::default();
    run_server(|method, params| match method {
        "memory.methods" => Ok(json!({
            "methods": [
                {
                    "method": "memory.inject",
                    "paramsSchemaRef": "bao.memory.inject_input/v1",
                    "resultSchemaRef": "bao.memory.inject_output/v1",
                    "notification": false
                },
                {
                    "method": "memory.extract",
                    "paramsSchemaRef": "bao.memory.extract_input/v1",
                    "resultSchemaRef": "bao.memory.mutation_plan/v1",
                    "notification": false
                }
            ]
        })),
        "memory.inject" => {
            let user_input = extract_user_input(params)?;
            let injected = hook.inject(&user_input);
            Ok(json!({
                "injected": injected,
            }))
        }
        "memory.extract" => {
            let plan = build_memory_extract_plan(params)?;
            serde_json::to_value(plan).map_err(|e| RpcError::internal(e.to_string()))
        }
        _ => Err(RpcError::method_not_found(method)),
    })
    .map_err(|e| e.to_string())
}

pub fn run_corrector_server() -> Result<(), String> {
    let hook = DefaultCorrectorHook;
    run_server(|method, params| match method {
        "corrector.methods" => Ok(json!({
            "methods": [
                {
                    "method": "corrector.validate_tool_args",
                    "paramsSchemaRef": "bao.toolcall.ir/v1",
                    "resultSchemaRef": "bao.corrector.validation/v1",
                    "notification": false
                },
                {
                    "method": "corrector.validate_tool_result",
                    "paramsSchemaRef": "bao.toolcall.result/v1",
                    "resultSchemaRef": "bao.corrector.validation/v1",
                    "notification": false
                },
                {
                    "method": "corrector.decide_retry",
                    "paramsSchemaRef": "bao.corrector.retry_input/v1",
                    "resultSchemaRef": "bao.corrector.retry_output/v1",
                    "notification": false
                }
            ]
        })),
        "corrector.validate_tool_args" => {
            let tool_call: ToolCallIrV1 = serde_json::from_value(params.clone())
                .map_err(|e| RpcError::invalid_params(e.to_string()))?;
            match hook.validate_tool_args(&tool_call) {
                Ok(()) => Ok(json!({ "ok": true })),
                Err(err) => Ok(json!({
                    "ok": false,
                    "error": err,
                })),
            }
        }
        "corrector.validate_tool_result" => validate_tool_result_payload(params),
        "corrector.decide_retry" => decide_retry_payload(params),
        _ => Err(RpcError::method_not_found(method)),
    })
    .map_err(|e| e.to_string())
}

fn validate_tool_result_payload(params: &Value) -> Result<Value, RpcError> {
    let ok = params
        .get("ok")
        .and_then(Value::as_bool)
        .ok_or_else(|| RpcError::invalid_params("missing ok boolean field"))?;

    if ok {
        return Ok(json!({ "ok": true }));
    }

    let error = params
        .get("error")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|v| !v.is_empty())
        .unwrap_or("tool execution failed");

    Ok(json!({
        "ok": false,
        "error": error,
    }))
}

fn decide_retry_payload(params: &Value) -> Result<Value, RpcError> {
    let attempt = params
        .get("attempt")
        .and_then(Value::as_i64)
        .unwrap_or(1)
        .max(1);
    let max_attempts = params
        .get("maxAttempts")
        .and_then(Value::as_i64)
        .unwrap_or(1)
        .max(1);
    let tool_ok = params.get("toolOk").and_then(Value::as_bool).unwrap_or(true);
    let validation_ok = params
        .get("validationOk")
        .and_then(Value::as_bool)
        .unwrap_or(true);

    let should_retry = attempt < max_attempts && (!tool_ok || !validation_ok);

    let reason = if should_retry {
        if !tool_ok && !validation_ok {
            "tool_and_validation_failed"
        } else if !tool_ok {
            "tool_failed"
        } else {
            "validation_failed"
        }
    } else if !tool_ok || !validation_ok {
        "max_attempts_reached"
    } else {
        "ok"
    };

    Ok(json!({
        "shouldRetry": should_retry,
        "reason": reason,
    }))
}

fn build_memory_extract_plan(params: &Value) -> Result<MemoryMutationPlanV1, RpcError> {
    let plan_id = make_id("plan");
    let user_input = params
        .get("userInput")
        .and_then(Value::as_str)
        .map(str::trim)
        .unwrap_or_default();

    if user_input.is_empty() || !should_extract_memory(user_input) {
        return Ok(MemoryMutationPlanV1 {
            planId: plan_id,
            mutations: vec![],
            dangerous: None,
        });
    }

    let title = shorten_title(user_input, 48);
    let memory = MemoryItemV1 {
        id: None,
        namespace: "chat.user".to_string(),
        kind: "fact".to_string(),
        title,
        content: Some(user_input.to_string()),
        json: None,
        score: Some(0.75),
        status: Some("active".to_string()),
        sourceHash: None,
    };
    let mutation = MemoryMutationV1 {
        op: MemoryMutationOpV1::UPSERT,
        idempotencyKey: make_id("idem"),
        reason: Some("explicit_memory_intent".to_string()),
        memory: Some(memory),
        supersede: None,
        delete: None,
        link: None,
    };

    Ok(MemoryMutationPlanV1 {
        planId: plan_id,
        mutations: vec![mutation],
        dangerous: None,
    })
}

fn should_extract_memory(input: &str) -> bool {
    let lower = input.to_lowercase();
    ["记住", "remember", "memory", "别忘", "保存"]
        .iter()
        .any(|kw| lower.contains(kw))
}

fn shorten_title(input: &str, limit: usize) -> String {
    let mut title = String::new();
    let mut count = 0usize;
    for ch in input.chars() {
        if count >= limit {
            break;
        }
        title.push(ch);
        count += 1;
    }
    if input.chars().count() > limit {
        title.push('…');
    }
    title
}

fn make_id(prefix: &str) -> String {
    let ts = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(0);
    format!("{prefix}_{ts}")
}

fn extract_user_input(params: &Value) -> Result<String, RpcError> {
    if let Some(v) = params.get("userInput").and_then(Value::as_str) {
        return Ok(v.to_string());
    }
    if let Some(v) = params.get("input").and_then(Value::as_str) {
        return Ok(v.to_string());
    }

    Err(RpcError::invalid_params(
        "missing userInput/input string field",
    ))
}

#[cfg(test)]
mod tests {
    use super::{build_memory_extract_plan, decide_retry_payload, validate_tool_result_payload};

    #[test]
    fn validate_tool_result_should_fail_when_ok_false() {
        let out = validate_tool_result_payload(&serde_json::json!({"ok": false}))
            .expect("result should return payload");
        assert_eq!(out.get("ok"), Some(&serde_json::json!(false)));
        assert_eq!(
            out.get("error"),
            Some(&serde_json::json!("tool execution failed"))
        );
    }

    #[test]
    fn decide_retry_should_retry_once_on_failure() {
        let out = decide_retry_payload(
            &serde_json::json!({"attempt": 1, "maxAttempts": 2, "toolOk": false}),
        )
        .expect("retry payload");
        assert_eq!(out.get("shouldRetry"), Some(&serde_json::json!(true)));
        assert_eq!(out.get("reason"), Some(&serde_json::json!("tool_failed")));
    }

    #[test]
    fn memory_extract_should_emit_plan_for_remember_intent() {
        let plan = build_memory_extract_plan(&serde_json::json!({
            "sessionId": "s1",
            "userInput": "请记住我喜欢乌龙茶",
            "assistantOutput": "好的"
        }))
        .expect("memory plan");

        assert_eq!(plan.mutations.len(), 1);
        assert!(plan.planId.starts_with("plan_"));
    }
}
