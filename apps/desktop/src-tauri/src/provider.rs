use bao_gateway::GatewayHandle;
use bao_plugin_host::ToolRunner;
use serde_json::{json, Map, Value};

use crate::dimsum_process::{self, ProcessRuntime};

#[derive(Debug, Clone)]
struct ProviderConfig {
    active: String,
    model: String,
    base_url: Option<String>,
    api_key: Option<String>,
    temperature: Option<f64>,
    max_tokens: Option<u32>,
}

#[derive(Debug, Clone)]
pub struct ProviderCallResult {
    pub provider: String,
    pub output: String,
}

pub async fn call_provider_via_runner(
    handle: &GatewayHandle,
    runner: &(dyn ToolRunner + Send + Sync),
    session_id: &str,
    input: &str,
) -> Result<ProviderCallResult, String> {
    let content = input.trim();
    if content.is_empty() {
        return Err("provider input cannot be empty".to_string());
    }

    let cfg = load_provider_config(handle).await?;
    let runtime = load_provider_runtime(handle, &cfg.active).await?;

    probe_provider_methods(runner, &runtime)?;

    let result = dimsum_process::run_jsonrpc(
        runner,
        &runtime,
        "provider.run",
        build_provider_params(session_id, content, &cfg),
        30_000,
    )?;

    let answer = parse_provider_result(&result)?;

    Ok(ProviderCallResult {
        provider: runtime.dimsum_id,
        output: answer,
    })
}

pub async fn resolve_provider_identity(
    handle: &GatewayHandle,
) -> Result<(String, String), String> {
    let cfg = load_provider_config(handle).await?;
    let runtime = load_provider_runtime(handle, &cfg.active).await?;
    Ok((runtime.dimsum_id, cfg.model))
}

async fn load_provider_config(handle: &GatewayHandle) -> Result<ProviderConfig, String> {
    let event = handle
        .get_settings()
        .await
        .map_err(|e| format!("load settings failed: {e}"))?;

    let settings = event
        .payload
        .get("settings")
        .and_then(Value::as_array)
        .ok_or_else(|| "settings payload missing".to_string())?;

    let mut active = None;
    let mut model = None;
    let mut base_url = None;
    let mut api_key = None;
    let mut temperature = None;
    let mut max_tokens = None;

    for item in settings {
        let Some(key) = item.get("key").and_then(Value::as_str) else {
            continue;
        };
        let value = item.get("value").cloned().unwrap_or(Value::Null);
        match key {
            "provider.active" => {
                active = value
                    .as_str()
                    .map(str::trim)
                    .filter(|s| !s.is_empty())
                    .map(str::to_string)
            }
            "provider.model" => {
                model = value
                    .as_str()
                    .map(str::trim)
                    .filter(|s| !s.is_empty())
                    .map(str::to_string)
            }
            "provider.baseUrl" => {
                base_url = value
                    .as_str()
                    .map(str::trim)
                    .filter(|s| !s.is_empty())
                    .map(str::to_string)
            }
            "provider.apiKey" => {
                api_key = value
                    .as_str()
                    .map(str::trim)
                    .filter(|s| !s.is_empty())
                    .map(str::to_string)
            }
            "provider.temperature" => {
                temperature = value.as_f64();
            }
            "provider.maxTokens" => {
                max_tokens = value.as_u64().map(|v| v as u32);
            }
            _ => {}
        }
    }

    Ok(ProviderConfig {
        active: active.unwrap_or_else(|| "openai".to_string()),
        model: model.unwrap_or_else(|| "gpt-4.1-mini".to_string()),
        base_url,
        api_key,
        temperature,
        max_tokens,
    })
}

async fn load_provider_runtime(
    handle: &GatewayHandle,
    active: &str,
) -> Result<ProcessRuntime, String> {
    let target = normalize_provider_to_dimsum_id(active);

    if let Some(runtime) = dimsum_process::load_process_runtime(handle, &target).await? {
        return Ok(runtime);
    }

    Ok(default_runtime_for(&target))
}

fn normalize_provider_to_dimsum_id(active: &str) -> String {
    let value = active.trim();
    if value.starts_with("bao.bundled.provider.") {
        return value.to_string();
    }

    let low = value.to_lowercase();
    if low.contains("anthropic") {
        return "bao.bundled.provider.anthropic".to_string();
    }
    if low.contains("gemini") {
        return "bao.bundled.provider.gemini".to_string();
    }
    if low.contains("xai") {
        return "bao.bundled.provider.xai".to_string();
    }
    "bao.bundled.provider.openai".to_string()
}

fn default_runtime_for(dimsum_id: &str) -> ProcessRuntime {
    let bin = if dimsum_id.ends_with("anthropic") {
        "bao-provider-anthropic"
    } else if dimsum_id.ends_with("gemini") {
        "bao-provider-gemini"
    } else if dimsum_id.ends_with("xai") {
        "bao-provider-xai"
    } else {
        "bao-provider-openai"
    };

    ProcessRuntime {
        dimsum_id: dimsum_id.to_string(),
        command: "cargo".to_string(),
        args: vec![
            "run".to_string(),
            "-q".to_string(),
            "-p".to_string(),
            "bao-dimsum-process".to_string(),
            "--bin".to_string(),
            bin.to_string(),
            "--".to_string(),
        ],
    }
}

fn build_provider_params(session_id: &str, input: &str, cfg: &ProviderConfig) -> Value {
    let mut config = Map::new();
    config.insert("model".to_string(), Value::String(cfg.model.clone()));

    if let Some(v) = cfg.base_url.clone() {
        config.insert("baseUrl".to_string(), Value::String(v));
    }
    if let Some(v) = cfg.api_key.clone() {
        config.insert("apiKey".to_string(), Value::String(v));
    }
    if let Some(v) = cfg.temperature {
        config.insert("temperature".to_string(), Value::from(v));
    }
    if let Some(v) = cfg.max_tokens {
        config.insert("maxTokens".to_string(), Value::from(v));
    }

    json!({
      "sessionId": session_id,
      "messages": [
        {
          "role": "user",
          "content": input,
        }
      ],
      "config": Value::Object(config),
    })
}

fn parse_provider_result(result: &Value) -> Result<String, String> {
    if result.get("kind").and_then(Value::as_str) == Some("tool_call") {
        if let Some(tool_call) = result.get("toolCall").and_then(Value::as_object) {
            let name = tool_call
                .get("name")
                .and_then(Value::as_str)
                .unwrap_or("unknown_tool");
            let args = tool_call
                .get("args")
                .cloned()
                .unwrap_or_else(|| serde_json::json!({}));
            let pretty_args = serde_json::to_string_pretty(&args).unwrap_or_else(|_| args.to_string());
            return Ok(format!("provider 请求工具调用：{}\n{}", name, pretty_args));
        }
        return Err("provider response kind=tool_call but toolCall missing".to_string());
    }

    if let Some(message) = result.get("message").and_then(Value::as_str) {
        let text = message.trim();
        if !text.is_empty() {
            return Ok(text.to_string());
        }
    }

    Err("provider response missing message".to_string())
}

fn probe_provider_methods(
    runner: &(dyn ToolRunner + Send + Sync),
    runtime: &ProcessRuntime,
) -> Result<(), String> {
    let methods =
        dimsum_process::run_jsonrpc(runner, runtime, "provider.methods", json!({}), 10_000)?;

    if method_is_supported(&methods, "provider.run") {
        Ok(())
    } else {
        Err("provider.methods missing provider.run".to_string())
    }
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
    use super::{
        method_is_supported, normalize_provider_to_dimsum_id, parse_provider_result,
        resolve_provider_identity,
    };

    #[test]
    fn normalize_provider_should_map_short_names() {
        assert_eq!(
            normalize_provider_to_dimsum_id("openai"),
            "bao.bundled.provider.openai"
        );
        assert_eq!(
            normalize_provider_to_dimsum_id("anthropic"),
            "bao.bundled.provider.anthropic"
        );
        assert_eq!(
            normalize_provider_to_dimsum_id("gemini"),
            "bao.bundled.provider.gemini"
        );
        assert_eq!(
            normalize_provider_to_dimsum_id("xai"),
            "bao.bundled.provider.xai"
        );
    }

    #[test]
    fn parse_provider_result_should_extract_message() {
        let out = parse_provider_result(&serde_json::json!({"message": "hello"})).expect("parse");
        assert_eq!(out, "hello");
    }

    #[test]
    fn parse_provider_result_should_extract_tool_call() {
        let out = parse_provider_result(&serde_json::json!({
            "kind": "tool_call",
            "toolCall": {
                "id": "tc_1",
                "name": "shell.exec",
                "args": {"command": "echo", "args": ["hi"]},
                "source": {"provider": "openai", "model": "gpt-4.1-mini"}
            }
        }))
        .expect("parse tool_call");
        assert!(out.contains("provider 请求工具调用：shell.exec"));
        assert!(out.contains("\"command\": \"echo\""));
    }

    #[test]
    fn method_is_supported_should_detect_target() {
        let methods = serde_json::json!({
            "methods": [
                {"method": "provider.methods"},
                {"method": "provider.run"}
            ]
        });
        assert!(method_is_supported(&methods, "provider.run"));
        assert!(!method_is_supported(&methods, "provider.delta"));
    }

    #[tokio::test]
    async fn resolve_provider_identity_should_return_runtime_and_model_defaults() {
        let unique = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .expect("time")
            .as_nanos();
        let sqlite_path =
            std::env::temp_dir().join(format!("bao_provider_meta_test_{unique}.sqlite"));

        let (_gateway, handle) =
            bao_gateway::GatewayServer::open(sqlite_path.to_string_lossy().to_string())
                .expect("open gateway");

        let (provider, model) = resolve_provider_identity(&handle)
            .await
            .expect("resolve provider identity");

        assert_eq!(provider, "bao.bundled.provider.openai");
        assert_eq!(model, "gpt-4.1-mini");

        let _ = std::fs::remove_file(sqlite_path);
    }

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
                .unwrap_or("");
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

            let stdout = if method == "provider.methods" {
                "{\"jsonrpc\":\"2.0\",\"id\":\"1\",\"result\":{\"methods\":[{\"method\":\"provider.run\"}]}}\n".to_string()
            } else if method == "provider.run" {
                "{\"jsonrpc\":\"2.0\",\"id\":\"1\",\"result\":{\"kind\":\"message\",\"message\":\"provider-ok\"}}\n".to_string()
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
    async fn call_provider_via_runner_should_use_provider_process_runtime() {
        let unique = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .expect("time")
            .as_nanos();
        let sqlite_path = std::env::temp_dir().join(format!("bao_provider_test_{unique}.sqlite"));

        let (_gateway, handle) =
            bao_gateway::GatewayServer::open(sqlite_path.to_string_lossy().to_string())
                .expect("open gateway");

        let runner = TestRunner;
        let out = super::call_provider_via_runner(&handle, &runner, "s1", "hello")
            .await
            .expect("call provider");

        assert_eq!(out.provider, "bao.bundled.provider.openai");
        assert_eq!(out.output, "provider-ok");

        let _ = std::fs::remove_file(sqlite_path);
    }
}
