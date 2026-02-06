use bao_gateway::GatewayHandle;
use bao_plugin_host::ToolRunner;
use serde_json::{json, Value};

#[derive(Debug, Clone)]
pub struct ProcessRuntime {
    pub dimsum_id: String,
    pub command: String,
    pub args: Vec<String>,
}

pub async fn load_process_runtime(
    handle: &GatewayHandle,
    target_dimsum_id: &str,
) -> Result<Option<ProcessRuntime>, String> {
    let event = handle
        .list_dimsums()
        .await
        .map_err(|e| format!("load dimsums failed: {e}"))?;

    let dimsums = event
        .payload
        .get("dimsums")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();

    Ok(dimsums.iter().find_map(|item| {
        let dimsum_id = item.get("dimsumId").and_then(Value::as_str)?;
        if dimsum_id != target_dimsum_id {
            return None;
        }

        let process = item
            .get("manifest")
            .and_then(|v| v.get("runtime"))
            .and_then(|v| v.get("process"))?;

        let command = process.get("command").and_then(Value::as_str)?.trim();
        if command.is_empty() {
            return None;
        }

        let args = process
            .get("args")
            .and_then(Value::as_array)
            .map(|arr| {
                arr.iter()
                    .filter_map(Value::as_str)
                    .map(str::to_string)
                    .collect::<Vec<_>>()
            })
            .unwrap_or_default();

        Some(ProcessRuntime {
            dimsum_id: dimsum_id.to_string(),
            command: command.to_string(),
            args,
        })
    }))
}

pub fn run_jsonrpc(
    runner: &(dyn ToolRunner + Send + Sync),
    runtime: &ProcessRuntime,
    method: &str,
    params: Value,
    timeout_ms: u64,
) -> Result<Value, String> {
    let request = json!({
      "jsonrpc": "2.0",
      "id": "bao-rpc-1",
      "method": method,
      "params": params,
    })
    .to_string();

    let run_args = json!({
      "command": runtime.command,
      "args": runtime.args,
      "timeoutMs": timeout_ms.clamp(1000, 60_000),
      "stdin": format!("{}\n", request),
    });

    let run = runner
        .run_tool(&runtime.dimsum_id, method, &run_args)
        .map_err(|e| format!("process run failed: {}", e.message))?;

    if !run.ok {
        let stderr = run
            .output
            .get("stderr")
            .and_then(Value::as_str)
            .unwrap_or_default();
        let stdout = run
            .output
            .get("stdout")
            .and_then(Value::as_str)
            .unwrap_or_default();
        let detail = if !stderr.trim().is_empty() {
            stderr.trim().to_string()
        } else if !stdout.trim().is_empty() {
            stdout.trim().to_string()
        } else {
            run.output.to_string()
        };
        return Err(format!("process failed: {detail}"));
    }

    let stdout = run
        .output
        .get("stdout")
        .and_then(Value::as_str)
        .ok_or_else(|| "process stdout missing".to_string())?;

    parse_jsonrpc_result(stdout)
}

pub fn parse_jsonrpc_result(stdout: &str) -> Result<Value, String> {
    let mut parse_errors: Vec<String> = Vec::new();

    for line in stdout
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty())
    {
        let json: Value = match serde_json::from_str(line) {
            Ok(v) => v,
            Err(err) => {
                parse_errors.push(format!("{line}: {err}"));
                continue;
            }
        };

        if json.get("jsonrpc").and_then(Value::as_str) != Some("2.0") {
            continue;
        }

        if let Some(error) = json.get("error") {
            let message = error
                .get("message")
                .and_then(Value::as_str)
                .unwrap_or("json-rpc error")
                .trim();
            return Err(message.to_string());
        }

        if let Some(result) = json.get("result") {
            return Ok(result.clone());
        }
    }

    if parse_errors.is_empty() {
        Err("json-rpc response missing valid result".to_string())
    } else {
        Err(format!(
            "json-rpc response parse failed: {}",
            parse_errors.join(" | ")
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::parse_jsonrpc_result;

    #[test]
    fn parse_jsonrpc_result_should_skip_log_lines() {
        let raw = "booting\n{\"jsonrpc\":\"2.0\",\"id\":1,\"result\":{\"ok\":true}}\n";
        let out = parse_jsonrpc_result(raw).expect("parse with logs");
        assert_eq!(out.get("ok"), Some(&serde_json::json!(true)));
    }

    #[test]
    fn parse_jsonrpc_result_should_return_error_message() {
        let raw = "{\"jsonrpc\":\"2.0\",\"id\":1,\"error\":{\"message\":\"boom\"}}\n";
        let err = parse_jsonrpc_result(raw).expect_err("should fail");
        assert!(err.contains("boom"));
    }
}
