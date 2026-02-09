use bao_gateway::GatewayHandle;
use bao_plugin_host::ToolRunner;
use reqwest::blocking::Client as HttpClient;
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

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ProviderKind {
    Openai,
    Anthropic,
    Gemini,
    Xai,
}

impl ProviderKind {
    fn from_active(active: &str) -> Self {
        let low = active.to_lowercase();
        if low.contains("anthropic") {
            Self::Anthropic
        } else if low.contains("gemini") {
            Self::Gemini
        } else if low.contains("xai") {
            Self::Xai
        } else {
            Self::Openai
        }
    }

    fn default_base_url(self) -> &'static str {
        match self {
            Self::Openai => "https://api.openai.com/v1",
            Self::Anthropic => "https://api.anthropic.com",
            Self::Gemini => "https://generativelanguage.googleapis.com",
            Self::Xai => "https://api.x.ai/v1",
        }
    }

    fn api_key_label(self) -> &'static str {
        match self {
            Self::Openai => "openai",
            Self::Anthropic => "anthropic",
            Self::Gemini => "gemini",
            Self::Xai => "xai",
        }
    }

    fn dimsum_id(self) -> &'static str {
        match self {
            Self::Openai => "bao.bundled.provider.openai",
            Self::Anthropic => "bao.bundled.provider.anthropic",
            Self::Gemini => "bao.bundled.provider.gemini",
            Self::Xai => "bao.bundled.provider.xai",
        }
    }

    fn process_bin(self) -> &'static str {
        match self {
            Self::Openai => "bao-provider-openai",
            Self::Anthropic => "bao-provider-anthropic",
            Self::Gemini => "bao-provider-gemini",
            Self::Xai => "bao-provider-xai",
        }
    }
}

#[derive(Debug, Clone)]
pub struct ProviderCallResult {
    pub provider: String,
    pub output: ProviderOutput,
}

#[derive(Debug, Clone)]
pub struct ProviderInputMessage {
    pub role: String,
    pub content: String,
    pub name: Option<String>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ProviderToolCall {
    pub id: String,
    pub name: String,
    pub args: Value,
}

#[derive(Debug, Clone, PartialEq)]
pub enum ProviderOutput {
    Message(String),
    ToolCall(ProviderToolCall),
    ToolCalls(Vec<ProviderToolCall>),
}

#[allow(dead_code)]
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

    call_provider_via_runner_with_messages(
        handle,
        runner,
        session_id,
        &[ProviderInputMessage {
            role: "user".to_string(),
            content: content.to_string(),
            name: None,
        }],
    )
    .await
}

pub async fn call_provider_via_runner_with_messages(
    handle: &GatewayHandle,
    runner: &(dyn ToolRunner + Send + Sync),
    session_id: &str,
    messages: &[ProviderInputMessage],
) -> Result<ProviderCallResult, String> {
    if messages.is_empty() {
        return Err("provider messages cannot be empty".to_string());
    }

    let cfg = load_provider_config(handle).await?;
    let runtime = load_provider_runtime(handle, &cfg.active).await?;

    probe_provider_methods(runner, &runtime)?;

    let result = dimsum_process::run_jsonrpc(
        runner,
        &runtime,
        "provider.run",
        build_provider_params_with_messages(session_id, messages, &cfg),
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

pub async fn preflight_provider_via_runner(
    handle: &GatewayHandle,
    _runner: &(dyn ToolRunner + Send + Sync),
) -> Result<(), String> {
    let cfg = load_provider_config(handle).await?;
    check_provider_connectivity(&cfg).map_err(|err| format_preflight_error(&err))
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
            "provider.active" => active = non_empty_string(&value),
            "provider.model" => model = non_empty_string(&value),
            "provider.baseUrl" => base_url = non_empty_string(&value),
            "provider.apiKey" => api_key = non_empty_string(&value),
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

    ProviderKind::from_active(value).dimsum_id().to_string()
}

fn default_runtime_for(dimsum_id: &str) -> ProcessRuntime {
    let bin = ProviderKind::from_active(dimsum_id).process_bin();

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

fn build_provider_params_with_messages(
    session_id: &str,
    messages: &[ProviderInputMessage],
    cfg: &ProviderConfig,
) -> Value {
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
      "messages": messages
          .iter()
          .map(|m| {
              let mut row = Map::new();
              row.insert("role".to_string(), Value::String(m.role.clone()));
              row.insert("content".to_string(), Value::String(m.content.clone()));
              if let Some(name) = m.name.clone() {
                  row.insert("name".to_string(), Value::String(name));
              }
              Value::Object(row)
          })
          .collect::<Vec<_>>(),
      "config": Value::Object(config),
    })
}

fn parse_provider_result(result: &Value) -> Result<ProviderOutput, String> {
    let kind = result.get("kind").and_then(Value::as_str);

    if kind == Some("tool_call") {
        let tool_call = result
            .get("toolCall")
            .ok_or_else(|| "provider response kind=tool_call but toolCall missing".to_string())?;
        return Ok(ProviderOutput::ToolCall(parse_provider_tool_call(tool_call)?));
    }

    if kind == Some("tool_calls") {
        let calls = result
            .get("toolCalls")
            .and_then(Value::as_array)
            .ok_or_else(|| "provider response kind=tool_calls but toolCalls missing".to_string())?;
        if calls.is_empty() {
            return Err("provider response toolCalls cannot be empty".to_string());
        }
        let parsed = calls
            .iter()
            .map(parse_provider_tool_call)
            .collect::<Result<Vec<_>, _>>()?;
        return Ok(ProviderOutput::ToolCalls(parsed));
    }

    if let Some(message) = result.get("message").and_then(Value::as_str) {
        let text = message.trim();
        if !text.is_empty() {
            return Ok(ProviderOutput::Message(text.to_string()));
        }
    }

    Err("provider response missing message".to_string())
}

fn parse_provider_tool_call(raw: &Value) -> Result<ProviderToolCall, String> {
    let name = raw
        .get("name")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|v| !v.is_empty())
        .ok_or_else(|| "provider toolCall.name is required".to_string())?
        .to_string();

    let args = raw
        .get("args")
        .cloned()
        .unwrap_or_else(|| serde_json::json!({}));

    let id = raw
        .get("id")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|v| !v.is_empty())
        .map(str::to_string)
        .unwrap_or_else(|| format!("tc_{}", time::OffsetDateTime::now_utc().unix_timestamp_nanos()));

    Ok(ProviderToolCall { id, name, args })
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

fn non_empty_string(value: &Value) -> Option<String> {
    value
        .as_str()
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(str::to_string)
}

fn check_provider_connectivity(cfg: &ProviderConfig) -> Result<(), String> {
    let kind = ProviderKind::from_active(&cfg.active);
    let key = load_api_key_from_cfg(kind.api_key_label(), cfg)?;
    let base = cfg
        .base_url
        .as_deref()
        .unwrap_or(kind.default_base_url())
        .trim_end_matches('/');

    let client = HttpClient::builder()
        .timeout(std::time::Duration::from_millis(2200))
        .build()
        .map_err(|e| format!("build connectivity client failed: {e}"))?;

    let rsp = match kind {
        ProviderKind::Anthropic => client
            .get(format!("{base}/v1/models"))
            .header("x-api-key", key)
            .header("anthropic-version", "2023-06-01")
            .send()
            .map_err(|e| format!("provider connectivity request failed: {e}"))?,
        ProviderKind::Gemini => client
            .get(format!("{base}/v1beta/models"))
            .query(&[("key", key)])
            .send()
            .map_err(|e| format!("provider connectivity request failed: {e}"))?,
        ProviderKind::Xai | ProviderKind::Openai => client
            .get(format!("{base}/models"))
            .bearer_auth(key)
            .send()
            .map_err(|e| format!("provider connectivity request failed: {e}"))?,
    };

    let status = rsp.status();
    let body = rsp
        .text()
        .unwrap_or_else(|_| "unable to read response body".to_string());
    if !status.is_success() {
        return Err(format!(
            "provider model list failed: http {} ({})",
            status.as_u16(),
            body
        ));
    }

    let payload: Value =
        serde_json::from_str(&body).map_err(|e| format!("provider model list invalid json: {e}"))?;
    let models = extract_model_ids(&payload, kind);
    ensure_model_available(&cfg.model, &models)
}

fn extract_model_ids(payload: &Value, kind: ProviderKind) -> Vec<String> {
    let mut out: Vec<String> = Vec::new();
    let mut seen: std::collections::HashSet<String> = std::collections::HashSet::new();

    let mut push = |raw: &str| {
        let value = raw.trim();
        if value.is_empty() {
            return;
        }
        let key = value.to_lowercase();
        if seen.insert(key) {
            out.push(value.to_string());
        }
        if let Some(stripped) = value.strip_prefix("models/") {
            let trimmed = stripped.trim();
            if !trimmed.is_empty() {
                let stripped_key = trimmed.to_lowercase();
                if seen.insert(stripped_key) {
                    out.push(trimmed.to_string());
                }
            }
        }
    };

    match kind {
        ProviderKind::Gemini => {
            if let Some(items) = payload.get("models").and_then(Value::as_array) {
                for item in items {
                    if let Some(name) = item.get("name").and_then(Value::as_str) {
                        push(name);
                    }
                    if let Some(id) = item.get("id").and_then(Value::as_str) {
                        push(id);
                    }
                }
            }
        }
        ProviderKind::Openai | ProviderKind::Anthropic | ProviderKind::Xai => {
            if let Some(items) = payload.get("data").and_then(Value::as_array) {
                for item in items {
                    if let Some(id) = item.get("id").and_then(Value::as_str) {
                        push(id);
                    }
                    if let Some(name) = item.get("name").and_then(Value::as_str) {
                        push(name);
                    }
                }
            }
        }
    }

    out
}

fn ensure_model_available(model: &str, available_models: &[String]) -> Result<(), String> {
    let selected = model.trim();
    if selected.is_empty() {
        return Err("model_invalid: model id is empty".to_string());
    }
    if available_models.is_empty() {
        return Err("provider model list is empty".to_string());
    }

    let selected_lower = selected.to_lowercase();
    let matched = available_models.iter().any(|item| {
        let lower = item.to_lowercase();
        lower == selected_lower || lower.ends_with(&format!("/{selected_lower}"))
    });

    if matched {
        Ok(())
    } else {
        Err(format!("model_invalid: model id `{selected}` not found"))
    }
}

fn load_api_key_from_cfg(kind: &str, cfg: &ProviderConfig) -> Result<String, String> {
    if let Some(v) = cfg
        .api_key
        .as_deref()
        .map(str::trim)
        .filter(|v| !v.is_empty())
    {
        return Ok(v.to_string());
    }

    let keys: &[&str] = match kind {
        "anthropic" => &["ANTHROPIC_API_KEY", "BAO_PROVIDER_API_KEY"],
        "gemini" => &["GEMINI_API_KEY", "GOOGLE_API_KEY", "BAO_PROVIDER_API_KEY"],
        "xai" => &["XAI_API_KEY", "BAO_PROVIDER_API_KEY"],
        _ => &["OPENAI_API_KEY", "BAO_PROVIDER_API_KEY"],
    };

    for key in keys {
        if let Ok(value) = std::env::var(key) {
            let trimmed = value.trim();
            if !trimmed.is_empty() {
                return Ok(trimmed.to_string());
            }
        }
    }

    Err("missing api key (config.apiKey or env)".to_string())
}

fn format_preflight_error(error: &str) -> String {
    let lower = error.to_lowercase();
    if lower.contains("missing api key") || lower.contains("401") || lower.contains("unauthorized") {
        return "auth_invalid: api key is invalid or missing".to_string();
    }
    if lower.contains("404") || (lower.contains("model") && lower.contains("not found")) {
        return "model_invalid: model id is not available".to_string();
    }
    if lower.contains("403") || lower.contains("forbidden") || lower.contains("permission") {
        return "permission_denied: provider access is denied".to_string();
    }
    if lower.contains("429") || lower.contains("rate") || lower.contains("quota") {
        return "rate_limited: too many requests".to_string();
    }
    if lower.contains("timeout") || lower.contains("timed out") {
        return "network_timeout: provider request timed out".to_string();
    }
    if lower.contains("http 5") || lower.contains("server") || lower.contains("overload") {
        return "provider_unavailable: provider service is temporarily unavailable".to_string();
    }
    format!("provider_preflight_failed: {error}")
}

#[cfg(test)]
mod tests {
    use super::{
        method_is_supported, normalize_provider_to_dimsum_id, parse_provider_result,
        resolve_provider_identity, ProviderOutput,
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
        assert_eq!(out, ProviderOutput::Message("hello".to_string()));
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
        match out {
            ProviderOutput::ToolCall(call) => {
                assert_eq!(call.name, "shell.exec");
                assert_eq!(call.id, "tc_1");
                assert_eq!(call.args.get("command"), Some(&serde_json::json!("echo")));
            }
            other => panic!("expected tool call output, got {other:?}"),
        }
    }

    #[test]
    fn parse_provider_result_should_extract_tool_calls_batch() {
        let out = parse_provider_result(&serde_json::json!({
            "kind": "tool_calls",
            "toolCalls": [
                {
                    "id": "tc_1",
                    "name": "shell.exec",
                    "args": {"command": "echo", "args": ["hi"]},
                    "source": {"provider": "openai", "model": "gpt-4.1-mini"}
                },
                {
                    "id": "tc_2",
                    "name": "resource.list",
                    "args": {"namespace": "skills"},
                    "source": {"provider": "openai", "model": "gpt-4.1-mini"}
                }
            ]
        }))
        .expect("parse tool_calls");
        match out {
            ProviderOutput::ToolCalls(calls) => {
                assert_eq!(calls.len(), 2);
                assert_eq!(calls[0].name, "shell.exec");
                assert_eq!(calls[1].name, "resource.list");
            }
            other => panic!("expected tool calls output, got {other:?}"),
        }
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
        assert_eq!(out.output, ProviderOutput::Message("provider-ok".to_string()));

        let _ = std::fs::remove_file(sqlite_path);
    }
}
