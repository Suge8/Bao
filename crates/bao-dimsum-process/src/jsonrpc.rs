use std::io::{self, BufRead, BufReader, Write};

use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Clone)]
pub struct RpcError {
    pub code: i64,
    pub message: String,
    pub data: Option<Value>,
}

impl RpcError {
    pub fn invalid_request(message: impl Into<String>) -> Self {
        Self {
            code: -32600,
            message: message.into(),
            data: None,
        }
    }

    pub fn method_not_found(method: &str) -> Self {
        Self {
            code: -32601,
            message: format!("method not found: {method}"),
            data: None,
        }
    }

    pub fn invalid_params(message: impl Into<String>) -> Self {
        Self {
            code: -32602,
            message: message.into(),
            data: None,
        }
    }

    pub fn internal(message: impl Into<String>) -> Self {
        Self {
            code: -32603,
            message: message.into(),
            data: None,
        }
    }
}

#[derive(Debug, Deserialize)]
struct JsonRpcRequest {
    jsonrpc: String,
    id: Option<Value>,
    method: String,
    #[serde(default)]
    params: Value,
}

#[derive(Debug, Serialize)]
struct JsonRpcErrorBody {
    code: i64,
    message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    data: Option<Value>,
}

#[derive(Debug, Serialize)]
struct JsonRpcResponse {
    jsonrpc: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    id: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    result: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<JsonRpcErrorBody>,
}

pub fn run_server<F>(mut handler: F) -> io::Result<()>
where
    F: FnMut(&str, &Value) -> Result<Value, RpcError>,
{
    let stdin = io::stdin();
    let stdout = io::stdout();
    let mut reader = BufReader::new(stdin.lock());
    let mut writer = io::BufWriter::new(stdout.lock());
    let mut line = String::new();

    loop {
        line.clear();
        let n = reader.read_line(&mut line)?;
        if n == 0 {
            break;
        }

        let raw = line.trim();
        if raw.is_empty() {
            continue;
        }

        let parsed = serde_json::from_str::<JsonRpcRequest>(raw);
        let request = match parsed {
            Ok(req) => req,
            Err(err) => {
                let rsp = JsonRpcResponse {
                    jsonrpc: "2.0",
                    id: None,
                    result: None,
                    error: Some(JsonRpcErrorBody {
                        code: -32700,
                        message: format!("parse error: {err}"),
                        data: None,
                    }),
                };
                serde_json::to_writer(&mut writer, &rsp)?;
                writer.write_all(b"\n")?;
                writer.flush()?;
                continue;
            }
        };

        if request.jsonrpc != "2.0" {
            let rsp = JsonRpcResponse {
                jsonrpc: "2.0",
                id: request.id,
                result: None,
                error: Some(JsonRpcErrorBody {
                    code: -32600,
                    message: "jsonrpc must be 2.0".to_string(),
                    data: None,
                }),
            };
            serde_json::to_writer(&mut writer, &rsp)?;
            writer.write_all(b"\n")?;
            writer.flush()?;
            continue;
        }

        let is_notification = request.id.is_none();
        let response = match handler(&request.method, &request.params) {
            Ok(result) => JsonRpcResponse {
                jsonrpc: "2.0",
                id: request.id,
                result: Some(result),
                error: None,
            },
            Err(err) => JsonRpcResponse {
                jsonrpc: "2.0",
                id: request.id,
                result: None,
                error: Some(JsonRpcErrorBody {
                    code: err.code,
                    message: err.message,
                    data: err.data,
                }),
            },
        };

        if !is_notification {
            serde_json::to_writer(&mut writer, &response)?;
            writer.write_all(b"\n")?;
            writer.flush()?;
        }
    }

    Ok(())
}
