use bao_gateway::GatewayHandle;
use bao_plugin_host::ToolRunner;
use serde_json::{json, Value};

use crate::dimsum_process::{self, ProcessRuntime};

const SKILLS_ADAPTER_DIMSUM_ID: &str = "bao.bundled.skills-adapter";

pub async fn list_resources_via_runner(
    handle: &GatewayHandle,
    runner: &(dyn ToolRunner + Send + Sync),
    namespace: String,
    prefix: Option<String>,
) -> Result<Value, String> {
    let ns = namespace.trim();
    if ns.is_empty() {
        return Err("namespace cannot be empty".to_string());
    }

    let runtime = load_skills_runtime(handle).await?;
    probe_resource_methods(runner, &runtime)?;

    dimsum_process::run_jsonrpc(
        runner,
        &runtime,
        "resource.list",
        json!({
          "namespace": ns,
          "prefix": prefix,
        }),
        30_000,
    )
}

pub async fn read_resource_via_runner(
    handle: &GatewayHandle,
    runner: &(dyn ToolRunner + Send + Sync),
    namespace: String,
    path: String,
) -> Result<Value, String> {
    let ns = namespace.trim();
    if ns.is_empty() {
        return Err("namespace cannot be empty".to_string());
    }
    let p = path.trim();
    if p.is_empty() {
        return Err("path cannot be empty".to_string());
    }

    let runtime = load_skills_runtime(handle).await?;
    probe_resource_methods(runner, &runtime)?;

    dimsum_process::run_jsonrpc(
        runner,
        &runtime,
        "resource.read",
        json!({
          "namespace": ns,
          "path": p,
        }),
        30_000,
    )
}

async fn load_skills_runtime(handle: &GatewayHandle) -> Result<ProcessRuntime, String> {
    if let Some(runtime) =
        dimsum_process::load_process_runtime(handle, SKILLS_ADAPTER_DIMSUM_ID).await?
    {
        return Ok(runtime);
    }

    Ok(ProcessRuntime {
        dimsum_id: SKILLS_ADAPTER_DIMSUM_ID.to_string(),
        command: "cargo".to_string(),
        args: vec![
            "run".to_string(),
            "-q".to_string(),
            "-p".to_string(),
            "bao-dimsum-process".to_string(),
            "--bin".to_string(),
            "bao-skills-adapter".to_string(),
            "--".to_string(),
        ],
    })
}

fn probe_resource_methods(
    runner: &(dyn ToolRunner + Send + Sync),
    runtime: &ProcessRuntime,
) -> Result<(), String> {
    let methods =
        dimsum_process::run_jsonrpc(runner, runtime, "resource.methods", json!({}), 10_000)?;

    if !method_is_supported(&methods, "resource.list") {
        return Err("resource.methods missing resource.list".to_string());
    }
    if !method_is_supported(&methods, "resource.read") {
        return Err("resource.methods missing resource.read".to_string());
    }
    Ok(())
}

fn method_is_supported(methods_result: &Value, method: &str) -> bool {
    methods_result
        .get("methods")
        .and_then(Value::as_array)
        .map(|methods| {
            methods.iter().any(|item| {
                item.get("method")
                    .and_then(Value::as_str)
                    .map(|name| name == method)
                    .unwrap_or(false)
            })
        })
        .unwrap_or(false)
}

#[cfg(test)]
mod tests {
    use super::method_is_supported;

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

            let stdout = if method == "resource.methods" {
                "{\"jsonrpc\":\"2.0\",\"id\":\"1\",\"result\":{\"methods\":[{\"method\":\"resource.list\"},{\"method\":\"resource.read\"}]}}\n".to_string()
            } else if method == "resource.list" {
                "{\"jsonrpc\":\"2.0\",\"id\":\"1\",\"result\":{\"items\":[{\"path\":\"a.txt\"}]}}\n"
                    .to_string()
            } else {
                "{\"jsonrpc\":\"2.0\",\"id\":\"1\",\"result\":{\"path\":\"a.txt\",\"text\":\"ok\"}}\n".to_string()
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

    #[test]
    fn method_is_supported_should_detect_resources() {
        let methods = serde_json::json!({
            "methods": [
                {"method": "resource.list"},
                {"method": "resource.read"}
            ]
        });
        assert!(method_is_supported(&methods, "resource.list"));
        assert!(method_is_supported(&methods, "resource.read"));
        assert!(!method_is_supported(&methods, "resource.write"));
    }

    #[tokio::test]
    async fn skills_adapter_should_list_and_read_resources() {
        let unique = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .expect("time")
            .as_nanos();
        let sqlite_path = std::env::temp_dir().join(format!("bao_skills_test_{unique}.sqlite"));

        let (_gateway, handle) =
            bao_gateway::GatewayServer::open(sqlite_path.to_string_lossy().to_string())
                .expect("open gateway");

        let runner = TestRunner;
        let list = super::list_resources_via_runner(
            &handle,
            &runner,
            "skills".to_string(),
            Some("x".to_string()),
        )
        .await
        .expect("list resources");
        assert_eq!(
            list.get("items")
                .and_then(serde_json::Value::as_array)
                .map(Vec::len),
            Some(1)
        );

        let read = super::read_resource_via_runner(
            &handle,
            &runner,
            "skills".to_string(),
            "a.txt".to_string(),
        )
        .await
        .expect("read resource");
        assert_eq!(read.get("text"), Some(&serde_json::json!("ok")));

        let _ = std::fs::remove_file(sqlite_path);
    }
}
