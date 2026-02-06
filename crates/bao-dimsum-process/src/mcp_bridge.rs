use std::collections::BTreeMap;
use std::io::{BufRead, BufReader, Read, Write};
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::time::Duration;

use reqwest::blocking::Client;
use serde::Deserialize;
use serde_json::{json, Value};

use crate::jsonrpc::{run_server, RpcError};

const DEFAULT_TIMEOUT_MS: u64 = 15_000;

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
struct BridgeServerConfig {
    #[serde(default)]
    transport: Option<String>,
    #[serde(default)]
    command: Option<String>,
    #[serde(default)]
    args: Option<Vec<String>>,
    #[serde(default)]
    cwd: Option<String>,
    #[serde(default)]
    env: Option<BTreeMap<String, String>>,
    #[serde(default)]
    url: Option<String>,
    #[serde(default)]
    headers: Option<BTreeMap<String, String>>,
    #[serde(default)]
    timeout_ms: Option<u64>,
}

impl BridgeServerConfig {
    fn transport(&self) -> &str {
        self.transport.as_deref().unwrap_or("stdio")
    }

    fn timeout_ms(&self) -> u64 {
        self.timeout_ms
            .unwrap_or(DEFAULT_TIMEOUT_MS)
            .clamp(1_000, 60_000)
    }
}

#[derive(Debug, Deserialize)]
struct BridgeListToolsInput {
    server: BridgeServerConfig,
}

#[derive(Debug, Deserialize)]
struct BridgeCallToolInput {
    server: BridgeServerConfig,
    name: String,
    #[serde(default)]
    arguments: Value,
}

pub fn run_mcp_bridge_server() -> Result<(), String> {
    run_server(|method, params| match method {
        "bridge.methods" => Ok(bridge_methods()),
        "bridge.ping" => Ok(json!({
            "ok": true,
            "supportedTransports": ["stdio", "http"],
        })),
        "bridge.list_tools" => handle_list_tools(params),
        "bridge.call_tool" => handle_call_tool(params),
        _ => Err(RpcError::method_not_found(method)),
    })
    .map_err(|e| e.to_string())
}

fn bridge_methods() -> Value {
    json!({
      "methods": [
        {
          "method": "bridge.methods",
          "paramsSchemaRef": "bao.provider.jsonrpc.methods/v1",
          "resultSchemaRef": "bao.provider.jsonrpc.methods/v1",
          "notification": false
        },
        {
          "method": "bridge.ping",
          "paramsSchemaRef": "bao.jsonrpc.envelope/v1",
          "resultSchemaRef": "bao.jsonrpc.envelope/v1",
          "notification": false
        },
        {
          "method": "bridge.list_tools",
          "paramsSchemaRef": "bao.jsonrpc.envelope/v1",
          "resultSchemaRef": "bao.jsonrpc.envelope/v1",
          "notification": false
        },
        {
          "method": "bridge.call_tool",
          "paramsSchemaRef": "bao.jsonrpc.envelope/v1",
          "resultSchemaRef": "bao.jsonrpc.envelope/v1",
          "notification": false
        }
      ]
    })
}

fn handle_list_tools(params: &Value) -> Result<Value, RpcError> {
    let input: BridgeListToolsInput = serde_json::from_value(params.clone())
        .map_err(|e| RpcError::invalid_params(e.to_string()))?;

    let result = match input.server.transport() {
        "stdio" => {
            let mut client = McpStdioClient::connect(&input.server)?;
            client.initialize()?;
            client.request("tools/list", json!({}))?
        }
        "http" => call_http_jsonrpc(&input.server, "tools/list", json!({}))?,
        other => {
            return Err(RpcError::invalid_params(format!(
                "unsupported MCP transport: {other}"
            )));
        }
    };

    Ok(json!({
        "tools": extract_tools(&result),
        "transport": input.server.transport(),
    }))
}

fn handle_call_tool(params: &Value) -> Result<Value, RpcError> {
    let input: BridgeCallToolInput = serde_json::from_value(params.clone())
        .map_err(|e| RpcError::invalid_params(e.to_string()))?;

    let name = input.name.trim();
    if name.is_empty() {
        return Err(RpcError::invalid_params("tool name cannot be empty"));
    }

    let request_params = json!({
        "name": name,
        "arguments": input.arguments,
    });

    let result = match input.server.transport() {
        "stdio" => {
            let mut client = McpStdioClient::connect(&input.server)?;
            client.initialize()?;
            client.request("tools/call", request_params)?
        }
        "http" => call_http_jsonrpc(&input.server, "tools/call", request_params)?,
        other => {
            return Err(RpcError::invalid_params(format!(
                "unsupported MCP transport: {other}"
            )));
        }
    };

    Ok(json!({
      "result": result,
      "transport": input.server.transport(),
    }))
}

fn extract_tools(result: &Value) -> Value {
    if let Some(tools) = result.get("tools") {
        return tools.clone();
    }
    if result.is_array() {
        return result.clone();
    }
    Value::Array(vec![])
}

fn call_http_jsonrpc(
    server: &BridgeServerConfig,
    method: &str,
    params: Value,
) -> Result<Value, RpcError> {
    let url = server
        .url
        .as_deref()
        .map(str::trim)
        .filter(|v| !v.is_empty())
        .ok_or_else(|| RpcError::invalid_params("http transport requires server.url"))?;

    let client = Client::builder()
        .timeout(Duration::from_millis(server.timeout_ms()))
        .build()
        .map_err(|e| RpcError::internal(format!("build http client failed: {e}")))?;

    let mut req = client.post(url).json(&json!({
        "jsonrpc": "2.0",
        "id": "bao-bridge-1",
        "method": method,
        "params": params,
    }));

    if let Some(headers) = server.headers.as_ref() {
        for (k, v) in headers {
            req = req.header(k, v);
        }
    }

    let rsp = req
        .send()
        .map_err(|e| RpcError::internal(format!("mcp http request failed: {e}")))?;

    let status = rsp.status();
    let body: Value = rsp
        .json()
        .map_err(|e| RpcError::internal(format!("mcp http response parse failed: {e}")))?;

    if !status.is_success() {
        let msg = extract_error_message(&body)
            .unwrap_or_else(|| format!("http status {}", status.as_u16()));
        return Err(RpcError::internal(format!("mcp http error: {msg}")));
    }

    if let Some(error) = body.get("error") {
        return Err(RpcError::internal(
            extract_error_message(error).unwrap_or_else(|| "mcp error".to_string()),
        ));
    }

    body.get("result")
        .cloned()
        .ok_or_else(|| RpcError::internal("mcp response missing result"))
}

fn extract_error_message(value: &Value) -> Option<String> {
    value
        .get("message")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|v| !v.is_empty())
        .map(str::to_string)
}

struct McpStdioClient {
    child: Child,
    stdin: ChildStdin,
    stdout: BufReader<ChildStdout>,
    next_id: u64,
}

impl McpStdioClient {
    fn connect(server: &BridgeServerConfig) -> Result<Self, RpcError> {
        let command = server
            .command
            .as_deref()
            .map(str::trim)
            .filter(|v| !v.is_empty())
            .ok_or_else(|| RpcError::invalid_params("stdio transport requires server.command"))?;

        let mut cmd = Command::new(command);
        if let Some(args) = server.args.as_ref() {
            cmd.args(args);
        }
        if let Some(cwd) = server.cwd.as_deref() {
            cmd.current_dir(cwd);
        }
        if let Some(env) = server.env.as_ref() {
            for (k, v) in env {
                cmd.env(k, v);
            }
        }
        cmd.stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());

        let mut child = cmd
            .spawn()
            .map_err(|e| RpcError::internal(format!("spawn mcp server failed: {e}")))?;

        let stdin = child
            .stdin
            .take()
            .ok_or_else(|| RpcError::internal("mcp server stdin unavailable"))?;
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| RpcError::internal("mcp server stdout unavailable"))?;

        Ok(Self {
            child,
            stdin,
            stdout: BufReader::new(stdout),
            next_id: 1,
        })
    }

    fn initialize(&mut self) -> Result<(), RpcError> {
        let _ = self.request(
            "initialize",
            json!({
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "bao-mcp-bridge",
                    "version": "0.1.0"
                }
            }),
        )?;

        self.notify("notifications/initialized", json!({}))?;
        Ok(())
    }

    fn notify(&mut self, method: &str, params: Value) -> Result<(), RpcError> {
        self.send_message(&json!({
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }))
    }

    fn request(&mut self, method: &str, params: Value) -> Result<Value, RpcError> {
        let id = self.next_id;
        self.next_id += 1;

        self.send_message(&json!({
            "jsonrpc": "2.0",
            "id": id,
            "method": method,
            "params": params,
        }))?;

        self.read_response(id)
    }

    fn send_message(&mut self, payload: &Value) -> Result<(), RpcError> {
        let body = serde_json::to_vec(payload)
            .map_err(|e| RpcError::internal(format!("serialize mcp request failed: {e}")))?;
        let header = format!("Content-Length: {}\r\n\r\n", body.len());

        self.stdin
            .write_all(header.as_bytes())
            .map_err(|e| RpcError::internal(format!("write mcp header failed: {e}")))?;
        self.stdin
            .write_all(&body)
            .map_err(|e| RpcError::internal(format!("write mcp body failed: {e}")))?;
        self.stdin
            .flush()
            .map_err(|e| RpcError::internal(format!("flush mcp stdin failed: {e}")))
    }

    fn read_response(&mut self, expected_id: u64) -> Result<Value, RpcError> {
        loop {
            let msg = read_mcp_message(&mut self.stdout)?;

            let Some(id) = msg.get("id") else {
                continue;
            };
            if !same_response_id(id, expected_id) {
                continue;
            }

            if let Some(error) = msg.get("error") {
                return Err(RpcError::internal(
                    extract_error_message(error).unwrap_or_else(|| "mcp error".to_string()),
                ));
            }

            return msg
                .get("result")
                .cloned()
                .ok_or_else(|| RpcError::internal("mcp response missing result"));
        }
    }
}

impl Drop for McpStdioClient {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

fn same_response_id(actual: &Value, expected: u64) -> bool {
    if let Some(n) = actual.as_u64() {
        return n == expected;
    }

    actual
        .as_str()
        .and_then(|s| s.parse::<u64>().ok())
        .map(|n| n == expected)
        .unwrap_or(false)
}

fn read_mcp_message(reader: &mut BufReader<ChildStdout>) -> Result<Value, RpcError> {
    let mut content_length: Option<usize> = None;

    loop {
        let mut line = String::new();
        let n = reader
            .read_line(&mut line)
            .map_err(|e| RpcError::internal(format!("read mcp header failed: {e}")))?;
        if n == 0 {
            return Err(RpcError::internal("mcp server closed stdout"));
        }

        let trimmed = line.trim_end_matches(['\r', '\n']);
        if trimmed.is_empty() {
            break;
        }

        let Some((name, value)) = trimmed.split_once(':') else {
            continue;
        };

        if name.trim().eq_ignore_ascii_case("content-length") {
            content_length = value.trim().parse::<usize>().ok();
        }
    }

    let len =
        content_length.ok_or_else(|| RpcError::internal("mcp header missing content-length"))?;
    let mut body = vec![0_u8; len];
    reader
        .read_exact(&mut body)
        .map_err(|e| RpcError::internal(format!("read mcp body failed: {e}")))?;

    serde_json::from_slice::<Value>(&body)
        .map_err(|e| RpcError::internal(format!("parse mcp body failed: {e}")))
}

#[cfg(test)]
mod tests {
    use super::{bridge_methods, same_response_id};

    #[test]
    fn bridge_methods_should_expose_runtime_calls() {
        let methods = bridge_methods();
        let arr = methods
            .get("methods")
            .and_then(serde_json::Value::as_array)
            .expect("methods array");

        assert!(arr
            .iter()
            .any(|m| m.get("method") == Some(&serde_json::json!("bridge.list_tools"))));
        assert!(arr
            .iter()
            .any(|m| m.get("method") == Some(&serde_json::json!("bridge.call_tool"))));
    }

    #[test]
    fn same_response_id_should_support_string_and_number() {
        assert!(same_response_id(&serde_json::json!(1), 1));
        assert!(same_response_id(&serde_json::json!("1"), 1));
        assert!(!same_response_id(&serde_json::json!("x"), 1));
    }
}
