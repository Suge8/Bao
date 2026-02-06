use bao_api::{MemoryMutationPlanV1, RouterOutputV1, ToolCallIrV1};
use bao_gateway::GatewayHandle;
use bao_plugin_host::ToolRunner;
use serde_json::Value;

use crate::dimsum_process::{self, ProcessRuntime};

const ROUTER_DIMSUM_ID: &str = "bao.bundled.router";
const MEMORY_DIMSUM_ID: &str = "bao.bundled.memory";
const CORRECTOR_DIMSUM_ID: &str = "bao.bundled.corrector";

pub async fn route_via_pipeline(
    handle: &GatewayHandle,
    runner: &(dyn ToolRunner + Send + Sync),
    user_input: &str,
) -> Result<RouterOutputV1, String> {
    let runtime = load_router_runtime(handle).await?;
    let result = dimsum_process::run_jsonrpc(
        runner,
        &runtime,
        "router.route",
        serde_json::json!({ "userInput": user_input }),
        30_000,
    )?;

    serde_json::from_value::<RouterOutputV1>(result)
        .map_err(|e| format!("router.route parse failed: {e}"))
}

pub async fn inject_memory_via_pipeline(
    handle: &GatewayHandle,
    runner: &(dyn ToolRunner + Send + Sync),
    provider_input: &str,
    memory_query: Option<String>,
) -> Result<String, String> {
    let runtime = load_memory_runtime(handle).await?;
    let result = dimsum_process::run_jsonrpc(
        runner,
        &runtime,
        "memory.inject",
        serde_json::json!({
          "userInput": provider_input,
          "memoryQuery": memory_query,
        }),
        30_000,
    )?;

    let injected = result
        .get("injected")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|v| !v.is_empty())
        .ok_or_else(|| "memory.inject missing injected output".to_string())?;

    Ok(injected.to_string())
}

pub async fn validate_tool_args_via_pipeline(
    handle: &GatewayHandle,
    runner: &(dyn ToolRunner + Send + Sync),
    tool_call_ir: &ToolCallIrV1,
) -> Result<(), String> {
    let runtime = load_corrector_runtime(handle).await?;
    let result = dimsum_process::run_jsonrpc(
        runner,
        &runtime,
        "corrector.validate_tool_args",
        serde_json::to_value(tool_call_ir).map_err(|e| format!("serialize tool call failed: {e}"))?,
        30_000,
    )?;

    let ok = result
        .get("ok")
        .and_then(Value::as_bool)
        .ok_or_else(|| "corrector.validate_tool_args missing ok field".to_string())?;

    if ok {
        return Ok(());
    }

    let err = result
        .get("error")
        .and_then(Value::as_str)
        .unwrap_or("tool args validation failed");
    Err(err.to_string())
}

pub async fn validate_tool_result_via_pipeline(
    handle: &GatewayHandle,
    runner: &(dyn ToolRunner + Send + Sync),
    payload: &Value,
) -> Result<(bool, Option<String>), String> {
    let runtime = load_corrector_runtime(handle).await?;
    let result = dimsum_process::run_jsonrpc(
        runner,
        &runtime,
        "corrector.validate_tool_result",
        payload.clone(),
        30_000,
    )?;

    let ok = result
        .get("ok")
        .and_then(Value::as_bool)
        .ok_or_else(|| "corrector.validate_tool_result missing ok field".to_string())?;
    let error = result
        .get("error")
        .and_then(Value::as_str)
        .map(str::to_string);

    Ok((ok, error))
}

pub async fn decide_retry_via_pipeline(
    handle: &GatewayHandle,
    runner: &(dyn ToolRunner + Send + Sync),
    payload: &Value,
) -> Result<(bool, Option<String>), String> {
    let runtime = load_corrector_runtime(handle).await?;
    let result = dimsum_process::run_jsonrpc(
        runner,
        &runtime,
        "corrector.decide_retry",
        payload.clone(),
        30_000,
    )?;

    let should_retry = result
        .get("shouldRetry")
        .and_then(Value::as_bool)
        .ok_or_else(|| "corrector.decide_retry missing shouldRetry field".to_string())?;
    let reason = result
        .get("reason")
        .and_then(Value::as_str)
        .map(str::to_string);

    Ok((should_retry, reason))
}

pub async fn extract_memory_plan_via_pipeline(
    handle: &GatewayHandle,
    runner: &(dyn ToolRunner + Send + Sync),
    payload: &Value,
) -> Result<MemoryMutationPlanV1, String> {
    let runtime = load_memory_runtime(handle).await?;
    let result = dimsum_process::run_jsonrpc(
        runner,
        &runtime,
        "memory.extract",
        payload.clone(),
        30_000,
    )?;

    if let Some(plan) = result.get("plan") {
        return serde_json::from_value::<MemoryMutationPlanV1>(plan.clone())
            .map_err(|e| format!("memory.extract plan parse failed: {e}"));
    }

    serde_json::from_value::<MemoryMutationPlanV1>(result)
        .map_err(|e| format!("memory.extract parse failed: {e}"))
}

async fn load_router_runtime(handle: &GatewayHandle) -> Result<ProcessRuntime, String> {
    if let Some(runtime) = dimsum_process::load_process_runtime(handle, ROUTER_DIMSUM_ID).await? {
        return Ok(runtime);
    }

    Ok(ProcessRuntime {
        dimsum_id: ROUTER_DIMSUM_ID.to_string(),
        command: "cargo".to_string(),
        args: vec![
            "run".to_string(),
            "-q".to_string(),
            "-p".to_string(),
            "bao-dimsum-process".to_string(),
            "--bin".to_string(),
            "bao-router-hook".to_string(),
            "--".to_string(),
        ],
    })
}

async fn load_memory_runtime(handle: &GatewayHandle) -> Result<ProcessRuntime, String> {
    if let Some(runtime) = dimsum_process::load_process_runtime(handle, MEMORY_DIMSUM_ID).await? {
        return Ok(runtime);
    }

    Ok(ProcessRuntime {
        dimsum_id: MEMORY_DIMSUM_ID.to_string(),
        command: "cargo".to_string(),
        args: vec![
            "run".to_string(),
            "-q".to_string(),
            "-p".to_string(),
            "bao-dimsum-process".to_string(),
            "--bin".to_string(),
            "bao-memory-hook".to_string(),
            "--".to_string(),
        ],
    })
}

async fn load_corrector_runtime(handle: &GatewayHandle) -> Result<ProcessRuntime, String> {
    if let Some(runtime) = dimsum_process::load_process_runtime(handle, CORRECTOR_DIMSUM_ID).await?
    {
        return Ok(runtime);
    }

    Ok(ProcessRuntime {
        dimsum_id: CORRECTOR_DIMSUM_ID.to_string(),
        command: "cargo".to_string(),
        args: vec![
            "run".to_string(),
            "-q".to_string(),
            "-p".to_string(),
            "bao-dimsum-process".to_string(),
            "--bin".to_string(),
            "bao-corrector-hook".to_string(),
            "--".to_string(),
        ],
    })
}

#[cfg(test)]
mod tests {
    use super::{
        decide_retry_via_pipeline, extract_memory_plan_via_pipeline, inject_memory_via_pipeline,
        route_via_pipeline, validate_tool_args_via_pipeline, validate_tool_result_via_pipeline,
    };

    #[derive(Clone)]
    struct TestRunner;

    impl bao_plugin_host::ToolRunner for TestRunner {
        fn run_tool(
            &self,
            _dimsum_id: &str,
            _tool_name: &str,
            args: &serde_json::Value,
        ) -> Result<bao_plugin_host::ToolRunResult, bao_plugin_host::PluginHostError> {
            let stdin = args
                .get("stdin")
                .and_then(serde_json::Value::as_str)
                .unwrap_or_default();
            let request: serde_json::Value = serde_json::from_str(stdin.trim()).map_err(|err| {
                bao_plugin_host::PluginHostError {
                    code: "invalid_request".to_string(),
                    message: err.to_string(),
                }
            })?;

            let method = request
                .get("method")
                .and_then(serde_json::Value::as_str)
                .unwrap_or_default();

            let stdout = if method == "router.route" {
                "{\"jsonrpc\":\"2.0\",\"id\":\"1\",\"result\":{\"matched\":true,\"confidence\":0.9,\"reasonCodes\":[\"explicit_tool\"],\"needsMemory\":false,\"toolName\":\"shell.exec\",\"toolArgs\":{\"command\":\"echo\"},\"quote\":\"/tool\",\"policy\":{\"mustTrigger\":true}}}\n".to_string()
            } else if method == "memory.inject" {
                "{\"jsonrpc\":\"2.0\",\"id\":\"1\",\"result\":{\"injected\":\"memory.injected: ok\"}}\n".to_string()
            } else if method == "corrector.validate_tool_args" {
                "{\"jsonrpc\":\"2.0\",\"id\":\"1\",\"result\":{\"ok\":true}}\n".to_string()
            } else if method == "corrector.validate_tool_result" {
                "{\"jsonrpc\":\"2.0\",\"id\":\"1\",\"result\":{\"ok\":true}}\n".to_string()
            } else if method == "corrector.decide_retry" {
                "{\"jsonrpc\":\"2.0\",\"id\":\"1\",\"result\":{\"shouldRetry\":false,\"reason\":\"ok\"}}\n".to_string()
            } else if method == "memory.extract" {
                "{\"jsonrpc\":\"2.0\",\"id\":\"1\",\"result\":{\"planId\":\"p1\",\"mutations\":[]}}\n".to_string()
            } else {
                "{\"jsonrpc\":\"2.0\",\"id\":\"1\",\"error\":{\"message\":\"method not found\"}}\n"
                    .to_string()
            };

            Ok(bao_plugin_host::ToolRunResult {
                ok: true,
                output: serde_json::json!({
                    "stdout": stdout,
                    "stderr": ""
                }),
            })
        }

        fn kill_group(&self, _group: &str) {}
    }

    #[tokio::test]
    async fn pipeline_hooks_should_route_inject_and_validate() {
        let unique = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .expect("time")
            .as_nanos();
        let sqlite_path = std::env::temp_dir().join(format!("bao_pipeline_test_{unique}.sqlite"));

        let (_gateway, handle) =
            bao_gateway::GatewayServer::open(sqlite_path.to_string_lossy().to_string())
                .expect("open gateway");

        let runner = TestRunner;

        let routed = route_via_pipeline(&handle, &runner, "/tool shell.exec {\"command\":\"echo\"}")
            .await
            .expect("route");
        assert!(routed.matched);
        assert_eq!(routed.toolName.as_deref(), Some("shell.exec"));

        let injected = inject_memory_via_pipeline(
            &handle,
            &runner,
            "user input",
            Some("memory query".to_string()),
        )
        .await
        .expect("inject");
        assert!(injected.contains("memory.injected"));

        let tc = bao_api::ToolCallIrV1 {
            id: "tc1".to_string(),
            name: "shell.exec".to_string(),
            args: serde_json::json!({"command": "echo"}),
            quote: Some("/tool".to_string()),
            source: bao_api::ToolCallSourceV1 {
                provider: "test".to_string(),
                model: "test".to_string(),
            },
        };
        validate_tool_args_via_pipeline(&handle, &runner, &tc)
            .await
            .expect("validate");

        let (result_ok, result_error) = validate_tool_result_via_pipeline(
            &handle,
            &runner,
            &serde_json::json!({"ok": true, "output": {"stdout": "ok"}}),
        )
        .await
        .expect("validate result");
        assert!(result_ok);
        assert!(result_error.is_none());

        let (should_retry, retry_reason) = decide_retry_via_pipeline(
            &handle,
            &runner,
            &serde_json::json!({"attempt": 1, "maxAttempts": 2, "toolOk": true}),
        )
        .await
        .expect("decide retry");
        assert!(!should_retry);
        assert_eq!(retry_reason.as_deref(), Some("ok"));

        let plan = extract_memory_plan_via_pipeline(
            &handle,
            &runner,
            &serde_json::json!({
                "sessionId": "s1",
                "userInput": "记住这个结论",
                "assistantOutput": "好的，我记住了"
            }),
        )
        .await
        .expect("extract memory");
        assert_eq!(plan.planId, "p1");
        assert!(plan.mutations.is_empty());

        let _ = std::fs::remove_file(sqlite_path);
    }
}
