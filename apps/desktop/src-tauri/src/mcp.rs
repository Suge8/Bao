use bao_gateway::GatewayHandle;
use bao_plugin_host::ToolRunner;
use serde_json::{json, Value};

use crate::dimsum_process::{self, ProcessRuntime};

const MCP_BRIDGE_DIMSUM_ID: &str = "bao.bundled.mcp-bridge";

pub async fn list_tools_via_runner(
    handle: &GatewayHandle,
    runner: &(dyn ToolRunner + Send + Sync),
    server: Value,
) -> Result<Value, String> {
    let runtime = load_mcp_bridge_runtime(handle).await?;
    dimsum_process::run_jsonrpc(
        runner,
        &runtime,
        "bridge.list_tools",
        json!({"server": server}),
        30_000,
    )
}

pub async fn call_tool_via_runner(
    handle: &GatewayHandle,
    runner: &(dyn ToolRunner + Send + Sync),
    server: Value,
    name: String,
    arguments: Value,
) -> Result<Value, String> {
    let method_name = name.trim().to_string();
    if method_name.is_empty() {
        return Err("mcp tool name cannot be empty".to_string());
    }

    let runtime = load_mcp_bridge_runtime(handle).await?;
    dimsum_process::run_jsonrpc(
        runner,
        &runtime,
        "bridge.call_tool",
        json!({
          "server": server,
          "name": method_name,
          "arguments": arguments,
        }),
        30_000,
    )
}

async fn load_mcp_bridge_runtime(handle: &GatewayHandle) -> Result<ProcessRuntime, String> {
    if let Some(runtime) =
        dimsum_process::load_process_runtime(handle, MCP_BRIDGE_DIMSUM_ID).await?
    {
        return Ok(runtime);
    }

    Ok(ProcessRuntime {
        dimsum_id: MCP_BRIDGE_DIMSUM_ID.to_string(),
        command: "cargo".to_string(),
        args: vec![
            "run".to_string(),
            "-q".to_string(),
            "-p".to_string(),
            "bao-dimsum-process".to_string(),
            "--bin".to_string(),
            "bao-mcp-bridge".to_string(),
            "--".to_string(),
        ],
    })
}

#[cfg(test)]
mod tests {
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
                    metadata: None,
                }
            })?;

            let method = request
                .get("method")
                .and_then(serde_json::Value::as_str)
                .unwrap_or_default();

            let stdout = if method == "bridge.list_tools" {
                "{\"jsonrpc\":\"2.0\",\"id\":\"1\",\"result\":{\"tools\":[{\"name\":\"fs.read\"}]}}\n".to_string()
            } else {
                "{\"jsonrpc\":\"2.0\",\"id\":\"1\",\"result\":{\"result\":{\"ok\":true}}}\n"
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
    async fn mcp_bridge_should_list_and_call_tools() {
        let unique = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .expect("time")
            .as_nanos();
        let sqlite_path = std::env::temp_dir().join(format!("bao_mcp_test_{unique}.sqlite"));

        let (_gateway, handle) =
            bao_gateway::GatewayServer::open(sqlite_path.to_string_lossy().to_string())
                .expect("open gateway");

        let runner = TestRunner;

        let list = super::list_tools_via_runner(
            &handle,
            &runner,
            serde_json::json!({"transport": "stdio", "command": "test-builtin-mcp"}),
        )
        .await
        .expect("list tools");
        assert_eq!(
            list.get("tools")
                .and_then(serde_json::Value::as_array)
                .map(Vec::len),
            Some(1)
        );

        let call = super::call_tool_via_runner(
            &handle,
            &runner,
            serde_json::json!({"transport": "stdio", "command": "test-builtin-mcp"}),
            "fs.read".to_string(),
            serde_json::json!({"path": "a.txt"}),
        )
        .await
        .expect("call tool");
        assert_eq!(
            call.get("result")
                .and_then(serde_json::Value::as_object)
                .and_then(|o| o.get("ok")),
            Some(&serde_json::json!(true))
        );

        let _ = std::fs::remove_file(sqlite_path);
    }
}
