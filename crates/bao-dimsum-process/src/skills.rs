use std::env;
use std::fs;
use std::path::{Path, PathBuf};

use base64::Engine;
use serde::Deserialize;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use walkdir::WalkDir;

use crate::jsonrpc::{run_server, RpcError};

#[derive(Debug, Deserialize)]
struct ResourceListInput {
    namespace: String,
    #[serde(default)]
    prefix: Option<String>,
}

#[derive(Debug, Deserialize)]
struct ResourceReadInput {
    namespace: String,
    path: String,
}

pub fn run_skills_server() -> Result<(), String> {
    run_server(|method, params| match method {
        "resource.list" => handle_list(params),
        "resource.read" => handle_read(params),
        "resource.methods" => Ok(json!({
          "methods": [
            {
              "method": "resource.list",
              "paramsSchemaRef": "bao.resource.list.input/v1",
              "resultSchemaRef": "bao.resource.list.output/v1",
              "notification": false
            },
            {
              "method": "resource.read",
              "paramsSchemaRef": "bao.resource.read.input/v1",
              "resultSchemaRef": "bao.resource.read.output/v1",
              "notification": false
            }
          ]
        })),
        _ => Err(RpcError::method_not_found(method)),
    })
    .map_err(|e| e.to_string())
}

fn resolve_namespace_root(namespace: &str) -> Result<PathBuf, RpcError> {
    if namespace == "skills" {
        if let Ok(v) = env::var("BAO_SKILLS_ROOT") {
            let p = PathBuf::from(v);
            if p.exists() {
                return Ok(p);
            }
        }

        if let Ok(home) = env::var("HOME") {
            let p = Path::new(&home).join(".agents/skills");
            if p.exists() {
                return Ok(p);
            }
        }

        return Err(RpcError::invalid_params(
            "skills namespace root not found; set BAO_SKILLS_ROOT",
        ));
    }

    if let Some(raw) = namespace.strip_prefix("dir:") {
        let p = PathBuf::from(raw);
        if p.exists() {
            return Ok(p);
        }
        return Err(RpcError::invalid_params(format!(
            "namespace dir not found: {raw}"
        )));
    }

    Err(RpcError::invalid_params(
        "unsupported namespace; use skills or dir:<abs_path>",
    ))
}

fn handle_list(params: &Value) -> Result<Value, RpcError> {
    let input: ResourceListInput = serde_json::from_value(params.clone())
        .map_err(|e| RpcError::invalid_params(e.to_string()))?;
    let root = resolve_namespace_root(&input.namespace)?;
    let root_canon = root
        .canonicalize()
        .map_err(|e| RpcError::internal(format!("canonicalize root failed: {e}")))?;

    let prefix = input.prefix.unwrap_or_default();

    let mut items = Vec::new();
    for entry in WalkDir::new(&root_canon)
        .into_iter()
        .filter_map(Result::ok)
        .filter(|e| e.file_type().is_file())
    {
        let path = entry.path();
        let rel = path
            .strip_prefix(&root_canon)
            .map_err(|e| RpcError::internal(format!("strip prefix failed: {e}")))?;
        let rel_str = normalize_rel_path(rel);
        if !prefix.is_empty() && !rel_str.starts_with(&prefix) {
            continue;
        }

        let bytes =
            fs::read(path).map_err(|e| RpcError::internal(format!("read resource failed: {e}")))?;
        let sha = sha256_hex(&bytes);
        let kind = if std::str::from_utf8(&bytes).is_ok() {
            "text"
        } else {
            "binary"
        };

        items.push(json!({
          "path": rel_str,
          "mime": guess_mime(path),
          "kind": kind,
          "sha256": sha,
          "size": bytes.len(),
        }));
    }

    Ok(json!({ "items": items }))
}

fn handle_read(params: &Value) -> Result<Value, RpcError> {
    let input: ResourceReadInput = serde_json::from_value(params.clone())
        .map_err(|e| RpcError::invalid_params(e.to_string()))?;
    let root = resolve_namespace_root(&input.namespace)?;
    let root_canon = root
        .canonicalize()
        .map_err(|e| RpcError::internal(format!("canonicalize root failed: {e}")))?;

    let candidate = root_canon.join(&input.path);
    let candidate_canon = candidate
        .canonicalize()
        .map_err(|e| RpcError::invalid_params(format!("resource path not found: {e}")))?;

    if !candidate_canon.starts_with(&root_canon) {
        return Err(RpcError::invalid_params("path escapes namespace root"));
    }

    let bytes = fs::read(&candidate_canon)
        .map_err(|e| RpcError::internal(format!("read resource failed: {e}")))?;
    let sha = sha256_hex(&bytes);
    let mime = guess_mime(&candidate_canon);

    if let Ok(text) = String::from_utf8(bytes.clone()) {
        Ok(json!({
          "path": input.path,
          "mime": mime,
          "kind": "text",
          "sha256": sha,
          "text": text,
        }))
    } else {
        Ok(json!({
          "path": input.path,
          "mime": mime,
          "kind": "binary",
          "sha256": sha,
          "base64": base64::engine::general_purpose::STANDARD.encode(bytes),
        }))
    }
}

fn normalize_rel_path(path: &Path) -> String {
    path.to_string_lossy().replace('\\', "/")
}

fn sha256_hex(bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    let out = hasher.finalize();
    out.iter().map(|b| format!("{b:02x}")).collect::<String>()
}

fn guess_mime(path: &Path) -> String {
    let ext = path
        .extension()
        .and_then(|e| e.to_str())
        .map(|s| s.to_lowercase())
        .unwrap_or_default();

    match ext.as_str() {
        "md" => "text/markdown",
        "txt" => "text/plain",
        "json" => "application/json",
        "yaml" | "yml" => "application/yaml",
        "ts" => "text/typescript",
        "tsx" => "text/tsx",
        "js" => "text/javascript",
        "py" => "text/x-python",
        "csv" => "text/csv",
        "png" => "image/png",
        "jpg" | "jpeg" => "image/jpeg",
        "svg" => "image/svg+xml",
        "wasm" => "application/wasm",
        _ => "application/octet-stream",
    }
    .to_string()
}

#[cfg(test)]
mod tests {
    use super::{handle_list, handle_read};
    use serde_json::json;

    #[test]
    fn list_and_read_should_work_for_dir_namespace() {
        let dir = tempfile::tempdir().expect("tempdir");
        let file = dir.path().join("a.txt");
        std::fs::write(&file, "hello").expect("write");

        let list = handle_list(&json!({
            "namespace": format!("dir:{}", dir.path().to_string_lossy()),
            "prefix": "a"
        }))
        .expect("list");
        let items = list
            .get("items")
            .and_then(serde_json::Value::as_array)
            .expect("items");
        assert_eq!(items.len(), 1);

        let read = handle_read(&json!({
            "namespace": format!("dir:{}", dir.path().to_string_lossy()),
            "path": "a.txt"
        }))
        .expect("read");
        assert_eq!(read.get("kind"), Some(&json!("text")));
        assert_eq!(read.get("text"), Some(&json!("hello")));
    }
}
