use std::env;

use reqwest::blocking::Client;
use serde::Deserialize;
use serde_json::{json, Value};

use crate::jsonrpc::{run_server, RpcError};

#[derive(Debug, Clone, Copy)]
pub enum ProviderKind {
    OpenAI,
    Anthropic,
    Gemini,
    XAi,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ProviderRunParams {
    #[allow(dead_code)]
    session_id: String,
    messages: Vec<ProviderMessage>,
    #[serde(default)]
    config: Option<ProviderConfig>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ProviderMessage {
    role: String,
    content: String,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ProviderConfig {
    #[serde(default)]
    model: Option<String>,
    #[serde(default)]
    base_url: Option<String>,
    #[serde(default)]
    api_key: Option<String>,
    #[serde(default)]
    temperature: Option<f64>,
    #[serde(default)]
    max_tokens: Option<u32>,
}

pub fn run_provider_server(kind: ProviderKind) -> Result<(), String> {
    run_server(|method, params| handle_provider_method(kind, method, params))
        .map_err(|e| e.to_string())
}

fn handle_provider_method(
    kind: ProviderKind,
    method: &str,
    params: &Value,
) -> Result<Value, RpcError> {
    match method {
        "provider.methods" => Ok(provider_methods()),
        "provider.delta" => provider_delta(params),
        "provider.cancel" => Err(RpcError::invalid_request(
            "provider.cancel is not supported in blocking mode; use kill-group cancellation",
        )),
        "provider.run" => run_provider(kind, params),
        _ => Err(RpcError::method_not_found(method)),
    }
}

fn provider_methods() -> Value {
    json!({
      "methods": [
        {
          "method": "provider.methods",
          "paramsSchemaRef": "bao.provider.jsonrpc.methods/v1",
          "resultSchemaRef": "bao.provider.jsonrpc.methods/v1",
          "notification": false
        },
        {
          "method": "provider.run",
          "paramsSchemaRef": "bao.provider.run.input/v1",
          "resultSchemaRef": "bao.provider.run.output/v1",
          "notification": false
        },
        {
          "method": "provider.delta",
          "paramsSchemaRef": "bao.provider.delta/v1",
          "resultSchemaRef": "bao.provider.delta/v1",
          "notification": false
        },
        {
          "method": "provider.cancel",
          "paramsSchemaRef": "bao.provider.cancel.input/v1",
          "resultSchemaRef": "bao.provider.cancel.output/v1",
          "notification": false
        }
      ]
    })
}

fn provider_delta(_params: &Value) -> Result<Value, RpcError> {
    Ok(json!({ "kind": "done" }))
}

fn run_provider(kind: ProviderKind, params: &Value) -> Result<Value, RpcError> {
    let parsed: ProviderRunParams = serde_json::from_value(params.clone())
        .map_err(|e| RpcError::invalid_params(e.to_string()))?;

    let prompt = build_prompt(&parsed.messages)
        .ok_or_else(|| RpcError::invalid_params("messages content cannot be empty"))?;

    let config = parsed.config.unwrap_or(ProviderConfig {
        model: None,
        base_url: None,
        api_key: None,
        temperature: None,
        max_tokens: None,
    });

    let answer = match kind {
        ProviderKind::OpenAI => call_openai_like(kind, &config, &parsed.messages, &prompt),
        ProviderKind::XAi => call_openai_like(kind, &config, &parsed.messages, &prompt),
        ProviderKind::Anthropic => call_anthropic(&config, &prompt),
        ProviderKind::Gemini => call_gemini(&config, &prompt),
    }
    .map_err(RpcError::internal)?;

    Ok(json!({
      "kind": "message",
      "message": answer,
    }))
}

fn build_prompt(messages: &[ProviderMessage]) -> Option<String> {
    let out = messages
        .iter()
        .filter_map(|m| {
            let content = m.content.trim();
            if content.is_empty() {
                None
            } else {
                Some(format!("{}: {}", m.role.trim(), content))
            }
        })
        .collect::<Vec<_>>()
        .join("\n");

    if out.trim().is_empty() {
        None
    } else {
        Some(out)
    }
}

fn default_model(kind: ProviderKind) -> &'static str {
    match kind {
        ProviderKind::OpenAI => "gpt-4.1-mini",
        ProviderKind::XAi => "grok-2-latest",
        ProviderKind::Anthropic => "claude-3-5-sonnet-latest",
        ProviderKind::Gemini => "gemini-1.5-flash",
    }
}

fn default_base(kind: ProviderKind) -> &'static str {
    match kind {
        ProviderKind::OpenAI => "https://api.openai.com/v1",
        ProviderKind::XAi => "https://api.x.ai/v1",
        ProviderKind::Anthropic => "https://api.anthropic.com",
        ProviderKind::Gemini => "https://generativelanguage.googleapis.com",
    }
}

fn load_api_key(kind: ProviderKind, cfg: &ProviderConfig) -> Result<String, String> {
    if let Some(v) = cfg
        .api_key
        .as_deref()
        .map(str::trim)
        .filter(|v| !v.is_empty())
    {
        return Ok(v.to_string());
    }

    let keys: &[&str] = match kind {
        ProviderKind::OpenAI => &["OPENAI_API_KEY", "BAO_PROVIDER_API_KEY"],
        ProviderKind::XAi => &["XAI_API_KEY", "BAO_PROVIDER_API_KEY"],
        ProviderKind::Anthropic => &["ANTHROPIC_API_KEY", "BAO_PROVIDER_API_KEY"],
        ProviderKind::Gemini => &["GEMINI_API_KEY", "GOOGLE_API_KEY", "BAO_PROVIDER_API_KEY"],
    };

    for key in keys {
        if let Ok(v) = env::var(key) {
            let vv = v.trim();
            if !vv.is_empty() {
                return Ok(vv.to_string());
            }
        }
    }

    Err("missing api key (config.apiKey or env)".to_string())
}

fn make_client() -> Result<Client, String> {
    Client::builder()
        .timeout(std::time::Duration::from_secs(30))
        .build()
        .map_err(|e| format!("build http client failed: {e}"))
}

fn call_openai_like(
    kind: ProviderKind,
    cfg: &ProviderConfig,
    messages: &[ProviderMessage],
    prompt: &str,
) -> Result<String, String> {
    let api_key = load_api_key(kind, cfg)?;
    let base = cfg
        .base_url
        .as_deref()
        .unwrap_or(default_base(kind))
        .trim_end_matches('/');
    let url = format!("{base}/chat/completions");

    let model = cfg.model.as_deref().unwrap_or(default_model(kind));

    let mut body = json!({
      "model": model,
      "messages": messages
          .iter()
          .map(|m| json!({"role": m.role, "content": m.content}))
          .collect::<Vec<_>>()
    });

    if body["messages"]
        .as_array()
        .map(|v| v.is_empty())
        .unwrap_or(true)
    {
        body["messages"] = json!([{"role": "user", "content": prompt}]);
    }

    if let Some(t) = cfg.temperature {
        body["temperature"] = json!(t);
    }
    if let Some(m) = cfg.max_tokens {
        body["max_tokens"] = json!(m);
    }

    let rsp = make_client()?
        .post(url)
        .bearer_auth(api_key)
        .header("content-type", "application/json")
        .json(&body)
        .send()
        .map_err(|e| format!("provider request failed: {e}"))?;

    let status = rsp.status();
    let data: Value = rsp
        .json()
        .map_err(|e| format!("provider response parse failed: {e}"))?;

    if !status.is_success() {
        let msg = data
            .get("error")
            .and_then(|e| e.get("message").or(Some(e)))
            .and_then(Value::as_str)
            .unwrap_or("upstream error");
        return Err(format!("provider http {}: {msg}", status.as_u16()));
    }

    data.get("choices")
        .and_then(Value::as_array)
        .and_then(|arr| arr.first())
        .and_then(|c| c.get("message"))
        .and_then(|m| m.get("content"))
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(str::to_string)
        .ok_or_else(|| "provider response missing choices[0].message.content".to_string())
}

fn call_anthropic(cfg: &ProviderConfig, prompt: &str) -> Result<String, String> {
    let api_key = load_api_key(ProviderKind::Anthropic, cfg)?;
    let base = cfg
        .base_url
        .as_deref()
        .unwrap_or(default_base(ProviderKind::Anthropic))
        .trim_end_matches('/');
    let url = format!("{base}/v1/messages");
    let model = cfg
        .model
        .as_deref()
        .unwrap_or(default_model(ProviderKind::Anthropic));

    let mut body = json!({
      "model": model,
      "max_tokens": cfg.max_tokens.unwrap_or(1024),
      "messages": [{"role": "user", "content": prompt}],
    });
    if let Some(t) = cfg.temperature {
        body["temperature"] = json!(t);
    }

    let rsp = make_client()?
        .post(url)
        .header("x-api-key", api_key)
        .header("anthropic-version", "2023-06-01")
        .header("content-type", "application/json")
        .json(&body)
        .send()
        .map_err(|e| format!("provider request failed: {e}"))?;

    let status = rsp.status();
    let data: Value = rsp
        .json()
        .map_err(|e| format!("provider response parse failed: {e}"))?;

    if !status.is_success() {
        let msg = data
            .get("error")
            .and_then(|e| e.get("message").or(Some(e)))
            .and_then(Value::as_str)
            .unwrap_or("upstream error");
        return Err(format!("provider http {}: {msg}", status.as_u16()));
    }

    data.get("content")
        .and_then(Value::as_array)
        .and_then(|arr| arr.first())
        .and_then(|v| v.get("text"))
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(str::to_string)
        .ok_or_else(|| "provider response missing content[0].text".to_string())
}

fn call_gemini(cfg: &ProviderConfig, prompt: &str) -> Result<String, String> {
    let api_key = load_api_key(ProviderKind::Gemini, cfg)?;
    let base = cfg
        .base_url
        .as_deref()
        .unwrap_or(default_base(ProviderKind::Gemini))
        .trim_end_matches('/');
    let model = cfg
        .model
        .as_deref()
        .unwrap_or(default_model(ProviderKind::Gemini));
    let url = format!("{base}/v1beta/models/{model}:generateContent");

    let mut body = json!({
      "contents": [
        {
          "role": "user",
          "parts": [{"text": prompt}]
        }
      ]
    });
    if let Some(t) = cfg.temperature {
        body["generationConfig"] = json!({"temperature": t});
    }

    let rsp = make_client()?
        .post(url)
        .query(&[("key", api_key)])
        .header("content-type", "application/json")
        .json(&body)
        .send()
        .map_err(|e| format!("provider request failed: {e}"))?;

    let status = rsp.status();
    let data: Value = rsp
        .json()
        .map_err(|e| format!("provider response parse failed: {e}"))?;

    if !status.is_success() {
        let msg = data
            .get("error")
            .and_then(|e| e.get("message").or(Some(e)))
            .and_then(Value::as_str)
            .unwrap_or("upstream error");
        return Err(format!("provider http {}: {msg}", status.as_u16()));
    }

    data.get("candidates")
        .and_then(Value::as_array)
        .and_then(|arr| arr.first())
        .and_then(|v| v.get("content"))
        .and_then(|v| v.get("parts"))
        .and_then(Value::as_array)
        .and_then(|arr| arr.first())
        .and_then(|v| v.get("text"))
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(str::to_string)
        .ok_or_else(|| "provider response missing candidates[0].content.parts[0].text".to_string())
}

#[cfg(test)]
mod tests {
    use super::{
        build_prompt, handle_provider_method, provider_methods, ProviderKind, ProviderMessage,
    };

    #[test]
    fn provider_methods_should_expose_required_methods() {
        let methods = provider_methods();
        let arr = methods
            .get("methods")
            .and_then(serde_json::Value::as_array)
            .expect("methods array");
        assert!(arr
            .iter()
            .any(|m| m.get("method") == Some(&serde_json::json!("provider.run"))));
        assert!(arr
            .iter()
            .any(|m| m.get("method") == Some(&serde_json::json!("provider.delta"))));
        assert!(arr
            .iter()
            .any(|m| m.get("method") == Some(&serde_json::json!("provider.cancel"))));
    }

    #[test]
    fn provider_methods_should_mark_all_methods_non_notification() {
        let methods = provider_methods();
        let arr = methods
            .get("methods")
            .and_then(serde_json::Value::as_array)
            .expect("methods array");

        assert!(arr.iter().all(|m| {
            m.get("notification")
                .and_then(serde_json::Value::as_bool)
                .is_some_and(|v| !v)
        }));
    }

    #[test]
    fn provider_cancel_should_return_invalid_request_error() {
        let err = handle_provider_method(
            ProviderKind::OpenAI,
            "provider.cancel",
            &serde_json::json!({}),
        )
        .expect_err("provider.cancel should fail in blocking mode");
        assert_eq!(err.code, -32600);
        assert!(err.message.contains("provider.cancel is not supported"));
    }

    #[test]
    fn provider_delta_should_return_done_chunk_in_blocking_mode() {
        let out = handle_provider_method(
            ProviderKind::OpenAI,
            "provider.delta",
            &serde_json::json!({}),
        )
        .expect("provider.delta should return done");
        assert_eq!(out.get("kind"), Some(&serde_json::json!("done")));
    }

    #[test]
    fn build_prompt_should_skip_empty_messages() {
        let prompt = build_prompt(&[
            ProviderMessage {
                role: "user".to_string(),
                content: "  hello  ".to_string(),
            },
            ProviderMessage {
                role: "assistant".to_string(),
                content: "".to_string(),
            },
        ])
        .expect("prompt");
        assert!(prompt.contains("user: hello"));
        assert!(!prompt.contains("assistant:"));
    }
}
